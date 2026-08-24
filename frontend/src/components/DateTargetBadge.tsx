import React from 'react'

// INCIDENT_CHANGE_PLAN Phase 4.2 — task date badge.
// Targets resolve at the run level (calc steps create them without a task_id),
// so consumers map a task's workflow_run_id to its run's targets.

export interface DateTargetInfo {
  id: number
  workflow_run_id: number
  step_id: number | null
  task_id: number | null
  target_key: string
  target_datetime: string
  status: string
}

const APPROACHING_HOURS = 24

type Urgency = 'met' | 'breached' | 'approaching' | 'on_track'

export const targetUrgency = (t: DateTargetInfo): Urgency => {
  if (t.status === 'met') return 'met'
  const remainingMs = new Date(t.target_datetime).getTime() - Date.now()
  if (t.status === 'breached' || remainingMs <= 0) return 'breached'
  return remainingMs < APPROACHING_HOURS * 3600000 ? 'approaching' : 'on_track'
}

const URGENCY_LABEL: Record<Urgency, string> = {
  met: 'Met',
  breached: 'Breached',
  approaching: 'Due soon',
  on_track: 'On track'
}

// Short human label used by both the badge and CSV export
export const describeTarget = (t?: DateTargetInfo): string => {
  if (!t) return ''
  return URGENCY_LABEL[targetUrgency(t)]
}

// Pick the most relevant target when a run has several:
// breached first, then pending by earliest deadline, met last.
export const pickRunTarget = (targets?: DateTargetInfo[]): DateTargetInfo | undefined => {
  if (!targets || targets.length === 0) return undefined
  const rank = (t: DateTargetInfo) => {
    switch (targetUrgency(t)) {
      case 'breached': return 0
      case 'approaching': return 1
      case 'on_track': return 2
      default: return 3
    }
  }
  return [...targets].sort((a, b) =>
    rank(a) - rank(b) ||
    new Date(a.target_datetime).getTime() - new Date(b.target_datetime).getTime()
  )[0]
}

interface DateTargetBadgeProps {
  target?: DateTargetInfo
}

export const DateTargetBadge: React.FC<DateTargetBadgeProps> = ({ target }) => {
  if (!target) return <>-</>

  const urgency = targetUrgency(target)
  const due = new Date(target.target_datetime)
  const title = `${target.target_key} — due ${due.toLocaleString()}`

  let badgeClass = 'badge-success'
  if (urgency === 'breached') badgeClass = 'badge-danger'
  else if (urgency === 'approaching') badgeClass = 'badge-warning'

  return (
    <span className={`badge ${badgeClass}`} title={title}>
      {URGENCY_LABEL[urgency]}
    </span>
  )
}
