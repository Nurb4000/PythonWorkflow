"""
Migration script: SQLite to PostgreSQL
"""
import sqlite3
import psycopg2
import psycopg2.extras
from typing import List, Dict, Any
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DatabaseMigration:
    """Migrate data from SQLite to PostgreSQL"""
    
    def __init__(self, sqlite_path: str, pg_config: dict):
        self.sqlite_path = sqlite_path
        self.pg_config = pg_config
    
    def migrate(self):
        """Perform full migration"""
        logger.info("Starting SQLite to PostgreSQL migration")
        
        # Connect to SQLite
        sqlite_conn = sqlite3.connect(self.sqlite_path)
        sqlite_conn.row_factory = sqlite3.Row
        
        # Get all tables
        tables = self._get_tables(sqlite_conn)
        logger.info(f"Found tables: {tables}")
        
        # Connect to PostgreSQL
        pg_conn = psycopg2.connect(**self.pg_config)
        pg_cursor = pg_conn.cursor()
        
        try:
            for table in tables:
                logger.info(f"Migrating table: {table}")
                self._migrate_table(sqlite_conn, pg_cursor, table)
            
            pg_conn.commit()
            logger.info("Migration completed successfully")
            
        except Exception as e:
            pg_conn.rollback()
            logger.error(f"Migration failed: {str(e)}")
            raise
        finally:
            pg_cursor.close()
            pg_conn.close()
            sqlite_conn.close()
    
    def _get_tables(self, conn: sqlite3.Connection) -> List[str]:
        """Get all table names from SQLite"""
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        tables = [row[0] for row in cursor.fetchall()]
        return tables
    
    def _migrate_table(self, sqlite_conn: sqlite3.Connection, pg_cursor, table: str):
        """Migrate a single table"""
        # Get SQLite schema
        sqlite_cursor = sqlite_conn.cursor()
        sqlite_cursor.execute(f"PRAGMA table_info({table})")
        columns = sqlite_cursor.fetchall()
        
        # Get all data from SQLite
        sqlite_cursor.execute(f"SELECT * FROM {table}")
        rows = sqlite_cursor.fetchall()
        
        if not rows:
            logger.info(f"No data in table {table}, skipping")
            return
        
        # Transform column names for PostgreSQL
        pg_columns = []
        for col in columns:
            col_name = col[1]
            col_type = self._transform_sqlite_type(col[2])
            pg_columns.append(f'"{col_name}" {col_type}')
        
        # Create table in PostgreSQL
        create_table_sql = f"""
        CREATE TABLE IF NOT EXISTS {table} (
            {', '.join(pg_columns)}
        )
        """
        pg_cursor.execute(create_table_sql)
        
        # Insert data
        placeholders = ', '.join(['%s'] * len(rows[0]))
        insert_sql = f"INSERT INTO {table} VALUES ({placeholders})"
        
        # Convert rows to tuples for PostgreSQL
        pg_rows = [tuple(row) for row in rows]
        psycopg2.extras.execute_batch(pg_cursor, insert_sql, pg_rows)
        
        logger.info(f"Migrated {len(pg_rows)} rows to {table}")


def _transform_sqlite_type(sqlite_type: str) -> str:
    """Transform SQLite types to PostgreSQL types"""
    type_map = {
        'INTEGER': 'INTEGER',
        'INT': 'INTEGER',
        'TEXT': 'TEXT',
        'VARCHAR': 'VARCHAR(255)',
        'BOOLEAN': 'BOOLEAN',
        'REAL': 'DOUBLE PRECISION',
        'FLOAT': 'DOUBLE PRECISION',
        'DATETIME': 'TIMESTAMP',
        'TIMESTAMP': 'TIMESTAMP',
    }
    
    # Handle VARCHAR with length
    if sqlite_type.startswith('VARCHAR'):
        return 'TEXT'  # PostgreSQL handles TEXT well
    
    return type_map.get(sqlite_type.upper(), 'TEXT')


if __name__ == "__main__":
    # Example usage
    config = {
        "host": "localhost",
        "port": 5432,
        "database": "workflow_db",
        "user": "workflow_user",
        "password": "password"
    }
    
    migrator = DatabaseMigration("workflow.db", config)
    migrator.migrate()
