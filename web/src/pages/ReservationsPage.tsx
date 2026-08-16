import { Bundle } from '../contracts/trip'

interface ReservationsPageProps {
  bundle: Bundle
}

export function ReservationsPage({ bundle }: ReservationsPageProps) {
  return (
    <section className="card" aria-label="預約與票券">
      <h2>預約與票券</h2>
      {bundle.reservations.length ? (
        <ul>
          {bundle.reservations.map((reservation) => (
            <li key={reservation.id}>
              <span>
                {reservation.day} · {reservation.time ?? '待補'} · {reservation.name || '固定預約'}
              </span>
              {reservation.unresolved ? '（地點與持續時間待補）' : ''}
            </li>
          ))}
        </ul>
      ) : (
        <p>目前無固定預約。</p>
      )}
      {bundle.reservations.filter((reservation) => reservation.unresolved).length > 0 ? (
        <p className="shell-message">有尚未補齊的預約關鍵欄位，請先補上。</p>
      ) : null}
    </section>
  )
}
