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

export function syncingChatsLabel(
  account: Account | null | undefined,
  loaded = 0,
): string {
  const name = [account?.first_name, account?.last_name]
    .map((part) => part?.trim())
    .filter((part): part is string => Boolean(part))
    .join(' ')
  const base = name ? `Syncing ${name} chats` : 'Syncing chats'
  return loaded > 0 ? `${base} · ${loaded} so far` : base
}
