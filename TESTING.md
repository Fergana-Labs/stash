# Testing

100% test coverage is the key to great vibe coding. Tests let you move fast, trust your instincts, and ship with confidence — without them, vibe coding is just yolo coding. With tests, it's a superpower.

## Framework

- **Frontend:** Vitest 4.x + @testing-library/react + jsdom
- **Config:** `frontend/vitest.config.ts`
- **Setup:** `frontend/vitest.setup.ts` (loads jest-dom matchers)

## Running Tests

```bash
cd frontend
npm test          # single run
npm run test:watch  # watch mode
```

## Test Layers

### Unit tests
- **What:** Pure functions, utilities, hooks, API client logic
- **Where:** `src/**/*.test.{ts,tsx}` alongside source files
- **When:** Every new function or module

### Integration tests
- **What:** Component interactions, form submissions, API flows
- **Where:** Same pattern, using @testing-library/react for rendering
- **When:** Multi-component workflows, form flows

### Regression tests
- **What:** Tests for bugs found during QA
- **Where:** `src/**/*.regression-*.test.{ts,tsx}`
- **When:** Every bug fix gets a regression test

## Conventions

- Co-locate tests with source files
- Name: `{module}.test.ts` or `{module}.test.tsx`
- Use `describe` / `it` blocks
- Import from `vitest` for test utilities
- Use `@testing-library/react` for component tests
- Use `vi.fn()` / `vi.mock()` for mocking
