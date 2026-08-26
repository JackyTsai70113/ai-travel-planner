import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const sourceRoot = resolve(process.cwd(), 'src')
const read = (path: string) => readFileSync(resolve(sourceRoot, path), 'utf8')
const packageJson = JSON.parse(readFileSync(resolve(process.cwd(), 'package.json'), 'utf8')) as { scripts: Record<string, string> }

describe('production architecture regression gates', () => {
  it('boots the site router and keeps TripApp as the canonical trip runtime', () => {
    const main = read('main.tsx')
    expect(main).toContain("from './app/site-router'")
    expect(main).not.toContain("from './App'")
    expect(existsSync(resolve(sourceRoot, 'App.tsx'))).toBe(false)
    expect(read('app/site-router.tsx')).toContain("from './TripApp'")
  })

  it('does not reintroduce trip-time writing, legacy storage, or fallback probing', () => {
    const sourceFiles = ['main.tsx', 'app/TripApp.tsx', 'hooks/useBundleLoader.ts']
      .map((path) => read(path)).join('\n')
    expect(sourceFiles).not.toMatch(/awaji_2026_/)
    expect(sourceFiles).not.toContain('candidates')
    expect(sourceFiles).not.toContain("'./public-bundle.json'")
    expect(existsSync(resolve(sourceRoot, 'hooks/useTripStorage.ts'))).toBe(false)
    expect(existsSync(resolve(sourceRoot, 'lib/storage/tripStorage.ts'))).toBe(false)
    expect(read('hooks/useBundleLoader.ts')).toContain('resolveBundleUrl')
  })

  it('keeps required quality commands executable', () => {
    for (const name of ['lint', 'typecheck', 'test', 'test:e2e', 'build']) {
      expect(packageJson.scripts[name]).toBeTruthy()
      expect(packageJson.scripts[name]).not.toMatch(/^echo\b/)
    }
  })
})
