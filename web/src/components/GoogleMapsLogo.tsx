import googleMapsLogo from '../assets/google-maps-logo-darkgray.svg'

/** Google 官方提供的歸屬標示圖檔，保持原始比例與外觀。 */
export function GoogleMapsLogo() {
  return <img className="google-maps-logo" src={googleMapsLogo} width={98} height={18} alt="Google Maps" draggable={false} />
}
