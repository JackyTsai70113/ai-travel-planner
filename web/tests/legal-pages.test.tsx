import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import SiteRouter from '../src/app/site-router'

afterEach(cleanup)

describe('公開政策頁面', () => {
  it('使用條款可獨立載入並連至 Google Maps Platform 條款', () => {
    window.history.replaceState({}, '', '/ai-travel-planner/terms.html')
    render(<SiteRouter />)
    expect(screen.getByRole('heading', { name: '使用條款' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Google Maps／Google Earth 使用者附加條款' })).toHaveAttribute('href', 'https://maps.google.com/help/terms_maps/')
  })

  it('隱私權政策可獨立載入並說明資料處理及 Google 政策', () => {
    window.history.replaceState({}, '', '/ai-travel-planner/privacy.html')
    render(<SiteRouter />)
    expect(screen.getByRole('heading', { name: '隱私權政策' })).toBeInTheDocument()
    expect(screen.getByText(/旅行需求可能包含目的地、日期、出發地/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Places API 政策' })).toHaveAttribute('href', 'https://developers.google.com/maps/documentation/places/web-service/policies')
  })
})
