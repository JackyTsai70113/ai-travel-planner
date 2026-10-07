export function siteRootUrl(currentUrl = window.location.href): URL {
  const url = new URL(currentUrl)
  const segments = url.pathname.split('/').filter(Boolean)
  const tripsIndex = segments.indexOf('trips')
  if (tripsIndex >= 0) {
    url.pathname = `/${segments.slice(0, tripsIndex).join('/')}${segments.slice(0, tripsIndex).length ? '/' : ''}`
  } else if (segments.at(-1)?.endsWith('.html')) {
    segments.pop()
    url.pathname = `/${segments.join('/')}${segments.length ? '/' : ''}`
  } else if (!url.pathname.endsWith('/')) {
    url.pathname = `${url.pathname}/`
  }
  url.search = ''
  url.hash = ''
  return url
}

export function sitePageUrl(page: 'terms' | 'privacy', currentUrl = window.location.href): string {
  return new URL(`${page}.html`, siteRootUrl(currentUrl)).toString()
}
