import type { Account } from './api'

export function accountDisplayName(account: Account): string {
  const name = [account.first_name, account.last_name].filter(Boolean).join(' ').trim()
  if (name) return name
  if (account.username) return `@${account.username}`
  return 'Telegram account'
}

export function formatAccountPhone(phone: string | null | undefined): string | null {
  if (!phone) return null
  const trimmed = phone.trim()
  if (!trimmed) return null
  return trimmed.startsWith('+') ? trimmed : `+${trimmed}`
}
