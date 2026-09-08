export function defaultUserAvatarUrl(name?: string) {
  return `https://ui-avatars.com/api/?name=${encodeURIComponent(name || 'User')}&background=random`
}

export function resolveUserAvatar(user?: { name?: string, avatar?: string } | null) {
  return user?.avatar || defaultUserAvatarUrl(user?.name)
}
