export function fetchFresh(url: string | URL): Promise<Response> {
  return fetch(url, { cache: 'no-store' })
}
