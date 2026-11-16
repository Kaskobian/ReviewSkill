# TypeScript/JavaScript Code Review Guide

> TypeScript code review guide covering the type system, generics, conditional types, strict mode, async/await patterns and more.

## Table of Contents

- [Type Safety Basics](#type-safety-basics)
- [Generic Patterns](#generic-patterns)
- [Advanced Types](#advanced-types)
- [Strict Mode Configuration](#strict-mode-configuration)
- [Async Handling](#async-handling)
- [Immutability](#immutability)
- [ESLint Rules](#eslint-rules)
- [Testing](#testing)
- [Module Resolution](#module-resolution)
- [TS 4.9+ / 5.x New Features](#ts-49--5x-new-features)
- [Review Checklist](#review-checklist)

---

## Type Safety Basics

### Avoid any

```typescript
// ❌ Using any defeats type safety
function processData(data: any) {
  return data.value;  // no type checking, may crash at runtime
}

// ✅ Use proper types
interface DataPayload {
  value: string;
}
function processData(data: DataPayload) {
  return data.value;
}

// ✅ Use unknown + type guards for unknown types
function processUnknown(data: unknown) {
  if (typeof data === 'object' && data !== null && 'value' in data && typeof data.value === 'string') {
    return data.value;
  }
  throw new Error('Invalid data');
}
```

### Type narrowing

```typescript
// ❌ Unsafe type assertion
function getLength(value: string | string[]) {
  return (value as string[]).length;  // hides the string case; works only because string also has .length
}

// ✅ Use type guards
function getLength(value: string | string[]): number {
  if (Array.isArray(value)) {
    return value.length;
  }
  return value.length;
}

// ✅ Use the in operator
interface Dog { bark(): void }
interface Cat { meow(): void }

function speak(animal: Dog | Cat) {
  if ('bark' in animal) {
    animal.bark();
  } else {
    animal.meow();
  }
}
```

### Literal types and as const

```typescript
// ❌ Type too wide
const config = {
  endpoint: '/api',
  method: 'GET'  // type is string
};

// ✅ Use as const to get literal types
const config = {
  endpoint: '/api',
  method: 'GET'
} as const;  // method type is 'GET'

// ✅ For function parameters
function request(method: 'GET' | 'POST', url: string) { ... }
request(config.method, config.endpoint);  // OK!
```

---

## Generic Patterns

### Basic generics

```typescript
// ❌ Duplicated code
function getFirstString(arr: string[]): string | undefined {
  return arr[0];
}
function getFirstNumber(arr: number[]): number | undefined {
  return arr[0];
}

// ✅ Use generics
function getFirst<T>(arr: T[]): T | undefined {
  return arr[0];
}
```

### Generic constraints

```typescript
// ❌ Unconstrained generic, cannot access properties
function getProperty<T>(obj: T, key: string) {
  return obj[key];  // Error: cannot index
}

// ✅ Constrain with keyof
function getProperty<T, K extends keyof T>(obj: T, key: K): T[K] {
  return obj[key];
}

const user = { name: 'Alice', age: 30 };
getProperty(user, 'name');  // return type is string
getProperty(user, 'age');   // return type is number
getProperty(user, 'foo');   // Error: 'foo' is not a key of user
```

### Generic defaults

```typescript
// ✅ Provide a sensible default type
interface ApiResponse<T = unknown> {
  data: T;
  status: number;
  message: string;
}

// The type argument can be omitted
const response: ApiResponse = { data: null, status: 200, message: 'OK' };
// or specified
const userResponse: ApiResponse<User> = { ... };
```

### Common generic utility types

```typescript
// ✅ Make good use of built-in utility types
interface User {
  id: number;
  name: string;
  email: string;
}

type PartialUser = Partial<User>;         // all properties optional
type RequiredUser = Required<User>;       // all properties required
type ReadonlyUser = Readonly<User>;       // all properties readonly
type UserKeys = keyof User;               // 'id' | 'name' | 'email'
type NameOnly = Pick<User, 'name'>;       // { name: string }
type WithoutId = Omit<User, 'id'>;        // { name: string; email: string }
type UserRecord = Record<string, User>;   // { [key: string]: User }
```

---

## Advanced Types

### Conditional types

```typescript
// ✅ Return different types depending on the input type
type IsString<T> = T extends string ? true : false;

type A = IsString<string>;  // true
type B = IsString<number>;  // false

// ✅ Extract the array element type
type ElementType<T> = T extends (infer U)[] ? U : never;

type Elem = ElementType<string[]>;  // string

// ✅ Extract the function return type (built-in ReturnType)
type MyReturnType<T> = T extends (...args: any[]) => infer R ? R : never;
```

### Mapped types

```typescript
// ✅ Transform all properties of an object type
type Nullable<T> = {
  [K in keyof T]: T[K] | null;
};

interface User {
  name: string;
  age: number;
}

type NullableUser = Nullable<User>;
// { name: string | null; age: number | null }

// ✅ Add a prefix
type Getters<T> = {
  [K in keyof T as `get${Capitalize<string & K>}`]: () => T[K];
};

type UserGetters = Getters<User>;
// { getName: () => string; getAge: () => number }
```

### Template literal types

```typescript
// ✅ Type-safe event names
type EventName = 'click' | 'focus' | 'blur';
type HandlerName = `on${Capitalize<EventName>}`;
// 'onClick' | 'onFocus' | 'onBlur'

// ✅ API route types
type ApiRoute = `/api/${string}`;
const route: ApiRoute = '/api/users';  // OK
const badRoute: ApiRoute = '/users';   // Error
```

### Discriminated Unions

```typescript
// ✅ Use a discriminant property for type safety
type Result<T, E> =
  | { success: true; data: T }
  | { success: false; error: E };

function handleResult(result: Result<User, Error>) {
  if (result.success) {
    console.log(result.data.name);  // TypeScript knows data exists
  } else {
    console.log(result.error.message);  // TypeScript knows error exists
  }
}

// ✅ Redux Action pattern
type Action =
  | { type: 'INCREMENT'; payload: number }
  | { type: 'DECREMENT'; payload: number }
  | { type: 'RESET' };

function reducer(state: number, action: Action): number {
  switch (action.type) {
    case 'INCREMENT':
      return state + action.payload;  // payload type is known
    case 'DECREMENT':
      return state - action.payload;
    case 'RESET':
      return 0;  // no payload here
  }
}
```

---

## Strict Mode Configuration

### Recommended tsconfig.json

```json
{
  "compilerOptions": {
    // ✅ Required strict options
    "strict": true,
    "noImplicitAny": true,
    "strictNullChecks": true,
    "strictFunctionTypes": true,
    "strictBindCallApply": true,
    "strictPropertyInitialization": true,
    "noImplicitThis": true,
    "useUnknownInCatchVariables": true,

    // ✅ Additional recommended options
    "noUncheckedIndexedAccess": true,
    "noImplicitReturns": true,
    "noFallthroughCasesInSwitch": true,
    "exactOptionalPropertyTypes": true,
    "noPropertyAccessFromIndexSignature": true
  }
}
```

### Effect of noUncheckedIndexedAccess

```typescript
// tsconfig: "noUncheckedIndexedAccess": true

const arr = [1, 2, 3];
const first = arr[0];  // type is number | undefined

// ❌ Using it directly may fail
console.log(first.toFixed(2));  // Error: possibly undefined

// ✅ Check first
if (first !== undefined) {
  console.log(first.toFixed(2));
}

// ✅ Or use a non-null assertion (when certain)
console.log(arr[0]!.toFixed(2));
```

---

## Async Handling

### Promise error handling

```typescript
// ❌ Not handling async errors
async function fetchUser(id: string) {
  const response = await fetch(`/api/users/${id}`);
  return response.json();  // network errors not handled
}

// ✅ Handle errors properly
async function fetchUser(id: string): Promise<User> {
  try {
    const response = await fetch(`/api/users/${id}`);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    return await response.json();
  } catch (error) {
    if (error instanceof Error) {
      throw new Error(`Failed to fetch user: ${error.message}`);
    }
    throw error;
  }
}
```

### Promise.all vs Promise.allSettled

```typescript
// ❌ Promise.all: one failure fails everything
async function fetchAllUsers(ids: string[]) {
  const users = await Promise.all(ids.map(fetchUser));
  return users;  // one failure fails them all
}

// ✅ Promise.allSettled gets all results
async function fetchAllUsers(ids: string[]) {
  const results = await Promise.allSettled(ids.map(fetchUser));

  const users: User[] = [];
  const errors: Error[] = [];

  for (const result of results) {
    if (result.status === 'fulfilled') {
      users.push(result.value);
    } else {
      errors.push(result.reason);
    }
  }

  return { users, errors };
}
```

### Handling race conditions

```typescript
// ❌ Race condition: an old request may overwrite a newer one
function useSearch() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);

  useEffect(() => {
    fetch(`/api/search?q=${query}`)
      .then(r => r.json())
      .then(setResults);  // an old request may return later!
  }, [query]);
}

// ✅ Use AbortController
function useSearch() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);

  useEffect(() => {
    const controller = new AbortController();

    fetch(`/api/search?q=${encodeURIComponent(query)}`, { signal: controller.signal })
      .then(r => r.json())
      .then(setResults)
      .catch(e => {
        if (e.name !== 'AbortError') throw e;
      });

    return () => controller.abort();
  }, [query]);
}
```

---

## Immutability

### Readonly and ReadonlyArray

```typescript
// ❌ Mutable parameters may be modified by accident
function processUsers(users: User[]) {
  users.sort((a, b) => a.name.localeCompare(b.name));  // mutates the original array!
  return users;
}

// ✅ Use readonly to prevent modification
function processUsers(users: readonly User[]): User[] {
  return [...users].sort((a, b) => a.name.localeCompare(b.name));
}

// ✅ Deep readonly
type DeepReadonly<T> = {
  readonly [K in keyof T]: T[K] extends object ? DeepReadonly<T[K]> : T[K];
};
```

### Immutable function parameters

```typescript
// ✅ Protect data with as const and readonly
function createConfig<T extends readonly string[]>(routes: T) {
  return routes;
}

const routes = createConfig(['home', 'about', 'contact'] as const);
// type is readonly ['home', 'about', 'contact']
```

---

## ESLint Rules

### Recommended @typescript-eslint rules

```javascript
// eslint.config.js (flat config, typescript-eslint v8)
import eslint from '@eslint/js';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  eslint.configs.recommended,
  // Rule sets that need type information; replaces the old recommended-requiring-type-checking
  tseslint.configs.recommendedTypeChecked,
  tseslint.configs.strictTypeChecked,
  {
    languageOptions: {
      parserOptions: {
        // Lets typed rules find the matching tsconfig automatically
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      // ✅ Type safety
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/no-unsafe-assignment': 'error',
      '@typescript-eslint/no-unsafe-member-access': 'error',
      '@typescript-eslint/no-unsafe-call': 'error',
      '@typescript-eslint/no-unsafe-return': 'error',

      // ✅ Best practices
      '@typescript-eslint/explicit-function-return-type': 'warn',
      '@typescript-eslint/no-floating-promises': 'error',
      '@typescript-eslint/await-thenable': 'error',
      '@typescript-eslint/no-misused-promises': 'error',

      // ✅ Code style
      '@typescript-eslint/consistent-type-imports': 'error',
      '@typescript-eslint/prefer-nullish-coalescing': 'error',
      '@typescript-eslint/prefer-optional-chain': 'error',
    },
  },
);
```

### Fixing common ESLint errors

```typescript
// ❌ no-floating-promises: Promises must be handled
async function save() { ... }
save();  // Error: unhandled Promise

// ✅ Handle explicitly
await save();
// or
save().catch(console.error);
// or ignore explicitly
void save();

// ❌ no-misused-promises: Promises cannot be used where a non-async callback is expected
const items = [1, 2, 3];
items.forEach(async (item) => {  // Error!
  await processItem(item);
});

// ✅ Use for...of
for (const item of items) {
  await processItem(item);
}
// or Promise.all
await Promise.all(items.map(processItem));
```

---

## Testing

### Choosing Vitest vs Jest

```typescript
// ✅ Vitest recommended for new projects (Vite ecosystem integration, native ESM support)
// vitest.config.ts
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: true,
    environment: 'node',
    include: ['src/**/*.test.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov'],
    },
  },
});

// ✅ Existing Jest projects can stay; mind the config differences
// jest.config.ts
import type { Config } from 'jest';

const config: Config = {
  preset: 'ts-jest',
  testEnvironment: 'node',
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1',
  },
};
export default config;
```

### Type tests (tsd / expect-type)

```typescript
// ✅ Vitest's expectTypeOf (built on expect-type) verifies type inference
import { expectTypeOf } from 'vitest';

function getFirst<T>(arr: T[]): T | undefined {
  return arr[0];
}

it('should infer correct return type', () => {
  const result = getFirst([1, 2, 3]);
  expectTypeOf(result).toEqualTypeOf<number | undefined>();
});

// ✅ Verify function signatures
const fn = (a: string, b: number) => a.repeat(b);
expectTypeOf(fn).parameters.toEqualTypeOf<[string, number]>();
expectTypeOf(fn).returns.toBeString();

// ✅ Type mismatches fail at compile time, not at runtime
const result = getFirst(['a', 'b']);
// @ts-expect-error: type mismatch
expectTypeOf(result).toEqualTypeOf<number>();
```

### Snapshot testing best practices

```typescript
// ✅ Snapshots suit: stable output structures, config objects, error messages
it('should match serialized config', () => {
  const config = createAppConfig();
  expect(config).toMatchSnapshot();
});

// ❌ Avoid: large objects, dynamic data, random values
it('should not snapshot large payloads', () => {
  const hugePayload = { users: generateRandomUsers(1000) };
  // overly long snapshots are hard to review; the intent of changes is unclear
});

// ✅ Use inline snapshots for small fragments
it('should generate correct error message', () => {
  expect(formatError('INVALID_INPUT')).toMatchInlineSnapshot(
    `"Error: Invalid input provided"`
  );
});

// ✅ Use snapshot property matchers for dynamic values
it('should match user with generated id', () => {
  expect(createUser('Alice')).toMatchSnapshot({
    id: expect.any(String),
    createdAt: expect.any(Date),
  });
});
```

### Mocking strategy

```typescript
// ✅ Vitest: vi.mock is hoisted automatically
import { vi, describe, it, expect } from 'vitest';

vi.mock('./api', () => ({
  fetchUser: vi.fn().mockResolvedValue({ id: 1, name: 'Alice' }),
}));

it('should display user', async () => {
  const { fetchUser } = await import('./api');
  const user = await fetchUser('1');
  expect(user.name).toBe('Alice');
});

// ✅ Jest: jest.mock is hoisted automatically too
jest.mock('./database', () => ({
  query: jest.fn().mockResolvedValue([{ id: 1 }]),
}));

// ❌ Avoid partial mocks - tests the mock, not real behavior
jest.mock('./utils', () => ({
  ...jest.requireActual('./utils'),
  calculateTotal: jest.fn(), // the other functions are real, this one is fake
}));
```

### Test helpers

```typescript
// ✅ Use testing-library for DOM tests
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

it('should submit form', async () => {
  render(<LoginForm />);
  await userEvent.type(screen.getByLabelText('Email'), 'alice@example.com');
  await userEvent.click(screen.getByRole('button', { name: 'Submit' }));
  expect(screen.getByText('Welcome, Alice!')).toBeInTheDocument();
});

// ✅ Use MSW for API mocking (Mock Service Worker)
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';

const server = setupServer(
  http.get('/api/users/:id', ({ params }) => {
    return HttpResponse.json({ id: params.id, name: 'Alice' });
  })
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
```

---

## Module Resolution

### ESM vs CJS differences and pitfalls

```typescript
// ❌ CJS style is not available in ESM
// package.json: "type": "module"
const fs = require('fs');           // Error: require is not defined
module.exports = { foo: 'bar' };    // Error: module is not defined

// ✅ Correct ESM
import fs from 'node:fs';
export const foo = 'bar';

// ✅ Getting __dirname in ESM
import { fileURLToPath } from 'node:url';
import { dirname } from 'node:path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// ❌ Dynamic require in ESM
const moduleName = 'lodash';
const _ = require(moduleName); // Error!

// ✅ Dynamic import in ESM
const _ = await import(moduleName);
```

### tsconfig paths and path aliases

```json
// tsconfig.json
{
  "compilerOptions": {
    "paths": {
      "@/*": ["./src/*"],
      "@components/*": ["./src/components/*"],
      "@utils/*": ["./src/utils/*"]
    }
  }
}
```

```typescript
// ✅ Before aliases
import { Button } from '../../components/ui/Button';
import { formatDate } from '../../../utils/date';

// ✅ After aliases - clear and less likely to break when files move
import { Button } from '@components/ui/Button';
import { formatDate } from '@utils/date';
```

```typescript
// ⚠️ tsconfig paths only affect TS compilation, not runtime
// Needs alias resolution from the bundler (Vite, webpack) or tsx

// vite.config.ts
import { resolve } from 'node:path';
import { defineConfig } from 'vite';

export default defineConfig({
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
});

// ⚠️ When publishing an npm package, tsconfig paths are not resolved automatically
// Use tsc-alias or tsconfig-paths
```

### package.json exports field

```json
// package.json
{
  "name": "my-library",
  "exports": {
    ".": {
      "types": "./dist/index.d.ts",
      "import": "./dist/index.mjs",
      "require": "./dist/index.cjs"
    },
    "./utils": {
      "types": "./dist/utils.d.ts",
      "import": "./dist/utils.mjs",
      "require": "./dist/utils.cjs"
    }
  }
}
```

```typescript
// ✅ Consumer usage
import { foo } from 'my-library';        // resolves via the "." entry
import { bar } from 'my-library/utils';   // resolves via the "./utils" entry

// ❌ Paths not mapped in exports cannot be accessed
import { secret } from 'my-library/internal'; // Error!
```

### Dynamic import() and code splitting

```typescript
// ✅ Load modules conditionally
async function loadChartLibrary() {
  if (typeof window === 'undefined') return null; // skip during SSR
  const { Chart } = await import('chart.js');
  return Chart;
}

// ✅ React lazy-loaded component
const AdminPanel = lazy(() => import('./AdminPanel'));
// use with Suspense
<Suspense fallback={<Loading />}>
  <AdminPanel />
</Suspense>

// ✅ With error handling
const AdminPanel = lazy(() =>
  import('./AdminPanel').catch(() => ({
    default: () => <ErrorFallback />,
  }))
);
```

---

## TS 4.9+ / 5.x New Features

### The satisfies keyword (TS 4.9+)

```typescript
// ❌ Without satisfies: type too wide
const palette = {
  red: '#ff0000',
  green: '#00ff00',
  blue: '#0000ff',
};
// palette.red is string, losing the exact '#ff0000' value

// ✅ satisfies keeps literal types while validating the shape
const palette = {
  red: '#ff0000',
  green: '#00ff00',
  blue: '#0000ff',
} satisfies Record<string, `#${string}`>;

// palette.red is '#ff0000' (not string)
// but new properties are still validated against the format
```

```typescript
// ✅ satisfies to validate that an object matches an interface
interface UserConfig {
  theme: 'light' | 'dark';
  locale: string;
}

const config = {
  theme: 'dark',
  locale: 'en-US',
} satisfies UserConfig;
// config.theme is 'dark' (not 'light' | 'dark')
// all properties are type-checked via satisfies
```

### const type parameters (TS 5.0+)

```typescript
// ❌ Before: needed an as const assertion
function getRoutes<T extends readonly string[]>(routes: T) {
  return routes;
}
const routes = getRoutes(['home', 'about'] as const);

// ✅ TS 5.0+: const type parameters
function getRoutes<const T extends readonly string[]>(routes: T) {
  return routes;
}
const routes = getRoutes(['home', 'about']);
// routes is readonly ['home', 'about']
```

```typescript
// ✅ Real-world case: type-safe config objects
declare function createConfig<const T extends Record<string, unknown>>(
  config: T
): T;

const config = createConfig({
  api: { url: 'https://api.example.com', version: 2 },
  features: { newDashboard: true },
});
// config.api.url is 'https://api.example.com' (literal)
```

### Decorators (Stage 3 Decorators, TS 5.0+)

```typescript
// ✅ Stage 3 decorators (TS 5.0+, experimentalDecorators no longer needed)
function logged<This, Args extends unknown[], Return>(
  target: (this: This, ...args: Args) => Return,
  context: ClassMethodDecoratorContext
) {
  return function (this: This, ...args: Args): Return {
    console.log(`Calling ${String(context.name)} with`, args);
    return target.apply(this, args);
  };
}

class Calculator {
  @logged
  add(a: number, b: number): number {
    return a + b;
  }
}

// Output: Calling add with [1, 2]
new Calculator().add(1, 2);
```

```typescript
// ⚠️ Stage 3 decorators differ from the legacy experimentalDecorators
// Legacy: requires "experimentalDecorators": true in tsconfig
// New (TS 5.0+): supported by default, no extra config

// ❌ Legacy decorator signature (still supported but marked legacy)
function deprecated<T extends { new (...args: any[]): {} }>(constructor: T) {
  return class extends constructor { /* ... */ };
}

// ✅ New decorators distinguish by context type
function sealed<T extends { new (...args: any[]): {} }>(
  target: T,
  context: ClassDecoratorContext
) {
  // context.kind === 'class'
}
```

### using declarations (explicit resource management, TS 5.2+)

```typescript
// ✅ Use Symbol.dispose for automatic cleanup
class TempFile implements Disposable {
  private path: string;

  constructor() {
    this.path = `/tmp/file-${Date.now()}`;
  }

  write(data: string) { /* ... */ }

  [Symbol.dispose]() {
    // automatic cleanup - however the function exits (normally or by exception)
    fs.unlinkSync(this.path);
    console.log(`Cleaned up: ${this.path}`);
  }
}

function processFile() {
  using file = new TempFile(); // using declaration
  file.write('data');
  // file[Symbol.dispose]() is called automatically at the end of scope
}
```

```typescript
// ✅ AsyncDisposable for async resources (TS 5.2+)
class DatabaseConnection implements AsyncDisposable {
  private db!: sqlite3.Database;

  async connect() {
    this.db = new sqlite3.Database(':memory:');
  }

  async [Symbol.asyncDispose]() {
    // sqlite3 close() is callback-based, so wrap it in a Promise
    await new Promise<void>((resolve, reject) => this.db.close(err => (err ? reject(err) : resolve())));
  }
}

async function query() {
  await using conn = new DatabaseConnection(); // await using
  await conn.connect();
  // conn[Symbol.asyncDispose]() is awaited automatically at the end of scope
}
```

### Enum improvements (TS 5.0+)

```typescript
// ✅ All enums are now union enums (TS 5.0+)
enum Color {
  Red = 'RED',
  Green = 'GREEN',
}

// Before: enums with computed members were not union enums
// Now: an enum type is the union of its member types (Color.Red | Color.Green); a plain 'RED' string is still not assignable
const color: Color = Color.Red; // TypeScript now infers the Color type better
```

## Review Checklist

### Type System
- [ ] No `any` (use `unknown` + type guards instead)
- [ ] Interfaces and type definitions are complete and meaningfully named
- [ ] Generics used to improve reuse
- [ ] Union types are narrowed correctly
- [ ] Utility types used well (Partial, Pick, Omit, etc.)

### Generics
- [ ] Generics have appropriate constraints (extends)
- [ ] Generic parameters have sensible defaults
- [ ] Avoid over-genericizing (KISS)

### Strict Mode
- [ ] tsconfig.json enables strict: true
- [ ] noUncheckedIndexedAccess enabled
- [ ] No @ts-ignore (use @ts-expect-error instead)

### Async Code
- [ ] async functions have error handling
- [ ] Promise rejections are handled correctly
- [ ] No floating promises (unhandled Promises)
- [ ] Concurrent requests use Promise.all or Promise.allSettled
- [ ] Race conditions handled with AbortController

### Immutability
- [ ] Function parameters are not mutated directly
- [ ] Spread operator used to create new objects/arrays
- [ ] Consider the readonly modifier

### ESLint
- [ ] Uses @typescript-eslint/recommended
- [ ] No ESLint warnings or errors
- [ ] Uses consistent-type-imports
