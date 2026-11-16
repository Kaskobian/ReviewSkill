# Architecture Review Guide

A guide to reviewing architecture: is the code's structure sound and is the design appropriate?

## SOLID Principles Checklist

### S - Single Responsibility Principle (SRP)

**What to check:**
- Does this class/module have only one reason to change?
- Do all methods in the class serve the same purpose?
- Can you describe the class to a non-technical person in one sentence?

**Signals in code review:**
```
⚠️ Class name contains generic words like "And", "Manager", "Handler", "Processor"
⚠️ A class exceeds 200-300 lines of code
⚠️ A class has more than 5-7 public methods
⚠️ Different methods operate on completely different data
```

**Review questions:**
- "What is this class responsible for? Can it be split?"
- "If requirement X changes, which methods change? What about requirement Y?"

### O - Open/Closed Principle (OCP)

**What to check:**
- Does adding a feature require modifying existing code?
- Can new behavior be added through extension (inheritance, composition)?
- Are there long if/else or switch statements handling different types?

**Signals in code review:**
```
⚠️ switch/if-else chains handling different types
⚠️ Adding a feature requires changing core classes
⚠️ Type checks (instanceof, typeof) scattered through the code
```

**Review questions:**
- "To add a new X type, which files need to change?"
- "Will this switch statement grow with every new type?"

### L - Liskov Substitution Principle (LSP)

**What to check:**
- Can a subclass fully replace its parent?
- Does a subclass change the expected behavior of a parent method?
- Does a subclass throw exceptions the parent does not declare?

**Signals in code review:**
```
⚠️ Explicit type conversion (casting)
⚠️ Subclass method throws NotImplementedException
⚠️ Subclass method is empty or just returns
⚠️ Code using the base class has to check the concrete type
```

**Review questions:**
- "If the subclass replaces the parent, does calling code need to change?"
- "Does this method's behavior in the subclass honor the parent's contract?"

### I - Interface Segregation Principle (ISP)

**What to check:**
- Is the interface small and focused?
- Are implementers forced to implement methods they don't need?
- Do clients depend on methods they don't use?

**Signals in code review:**
```
⚠️ Interface has more than 5-7 methods
⚠️ Implementers have empty methods or throw NotImplementedException
⚠️ Interface name is too broad (IManager, IService)
⚠️ Different clients use only part of the interface
```

**Review questions:**
- "Does every implementer use every method of this interface?"
- "Can this large interface be split into smaller, specific ones?"

### D - Dependency Inversion Principle (DIP)

**What to check:**
- Do high-level modules depend on abstractions rather than concrete implementations?
- Is dependency injection used instead of directly calling new?
- Are abstractions defined by high-level modules rather than low-level ones?

**Signals in code review:**
```
⚠️ High-level module directly instantiates low-level concrete classes
⚠️ Imports concrete implementations instead of interfaces/abstract classes
⚠️ Configuration and connection strings hardcoded in business logic
⚠️ A class is hard to unit test
```

**Review questions:**
- "Can this class's dependencies be replaced by mocks in tests?"
- "How many places change if we swap the database/API implementation?"

---

## Identifying Architecture Anti-Patterns

### Critical Anti-Patterns

| Anti-pattern | Signals | Impact |
|--------|----------|------|
| **Big Ball of Mud** | No clear module boundaries; any code may call any other code | Hard to understand, change and test |
| **God Object** | A single class takes on too many responsibilities, knows too much, does too much | High coupling, hard to reuse and test |
| **Spaghetti Code** | Tangled control flow, goto or deep nesting, execution paths hard to follow | Hard to understand and maintain |
| **Lava Flow** | Old code nobody dares touch, no docs or tests | Accumulating technical debt |

### Design Anti-Patterns

| Anti-pattern | Signals | Recommendation |
|--------|----------|------|
| **Golden Hammer** | Same technology/pattern used for every problem | Choose the solution that fits the problem |
| **Gas Factory (over-engineering)** | Simple problems solved with complex solutions, design patterns overused | YAGNI: start simple, add complexity later |
| **Boat Anchor** | Unused code written "in case we need it later" | Delete unused code; write it when needed |
| **Copy-Paste Programming** | Same logic appears in several places | Extract a shared function or module |

### Review Comments

```markdown
🔴 [blocking] "The new class in this PR has 2000 lines; split it into several focused classes"
🟡 [important] "This logic is duplicated in 3 places; extract it into a shared function?"
💡 [suggestion] "This switch could be replaced by the Strategy pattern, making it easier to extend"
```

---

## Assessing Coupling and Cohesion

### Coupling Types (best to worst)

| Type | Description | Example |
|------|------|------|
| **Message coupling** ✅ | Modules interact only through messages / events, no shared data | `eventBus.publish(OrderPlaced)` |
| **Data coupling** ✅ | Passes only the simple data it needs via parameters | `calculate(price, quantity)` |
| **Stamp coupling** ⚠️ | Shares a complex structure but uses only part of it | Passes a whole User object but uses only name |
| **Control coupling** ⚠️ | Passes control flags that change behavior | `process(data, isAdmin=true)` |
| **Common coupling** ❌ | Shares global variables | Several modules read and write the same global state |
| **Content coupling** ❌ | Directly accesses another module's internals | Directly manipulates another class's private fields |

### Cohesion Types (best to worst)

| Type | Description | Quality |
|------|------|------|
| **Functional cohesion** | All elements accomplish a single task | ✅ Best |
| **Sequential cohesion** | Output of one step is input to the next | ✅ Good |
| **Communicational cohesion** | Operate on the same data | ⚠️ Acceptable |
| **Temporal cohesion** | Tasks executed at the same time | ⚠️ Poor |
| **Logical cohesion** | Logically related but functionally different | ❌ Bad |
| **Coincidental cohesion** | No meaningful relationship | ❌ Worst |

### Reference Metrics

```yaml
Coupling metrics:
  CBO (Coupling Between Objects):
    good: < 5
    warning: 5-10
    danger: > 10

  Ce (efferent coupling):
    description: how many external classes it depends on
    good: < 7

  Ca (afferent coupling):
    description: how many classes depend on it
    high value means: changes have wide impact; must stay stable

Cohesion metrics:
  LCOM4 (Lack of Cohesion of Methods):
    1: single responsibility ✅
    2-3: may need splitting ⚠️
    >3: should be split ❌
```

### Review Questions

- "How many other modules does this module depend on? Can that be reduced?"
- "How many other places are affected if this class changes?"
- "Do all methods of this class operate on the same data?"

---

## Layered Architecture Review

### Clean Architecture Layer Check

```
┌─────────────────────────────────────┐
│         Frameworks & Drivers        │ ← Outermost: Web, DB, UI
├─────────────────────────────────────┤
│         Interface Adapters          │ ← Controllers, Gateways, Presenters
├─────────────────────────────────────┤
│          Application Layer          │ ← Use Cases, Application Services
├─────────────────────────────────────┤
│            Domain Layer             │ ← Entities, Domain Services
└─────────────────────────────────────┘
          ↓ Dependencies point inward only (toward Domain) ↓
```

### Dependency Rule Check

**Core rule: source code dependencies may only point inward**

```typescript
// ❌ Violates the dependency rule: Domain layer depends on Infrastructure
// domain/User.ts
import { MySQLConnection } from '../infrastructure/database';

// ✅ Correct: Domain defines the interface, Infrastructure implements it
// domain/UserRepository.ts (interface)
interface UserRepository {
  findById(id: string): Promise<User>;
}

// infrastructure/MySQLUserRepository.ts (implementation)
class MySQLUserRepository implements UserRepository {
  findById(id: string): Promise<User> { /* ... */ }
}
```

### Review Checklist

**Layer boundaries:**
- [ ] Does the Domain layer have external dependencies (database, HTTP, file system)?
- [ ] Does the Application layer access the database or call external APIs directly?
- [ ] Does the Controller contain business logic?
- [ ] Are there cross-layer calls (UI calling a Repository directly)?

**Separation of concerns:**
- [ ] Is business logic separated from presentation logic?
- [ ] Is data access encapsulated in a dedicated layer?
- [ ] Is configuration and environment-specific code managed centrally?

### Review Comments

```markdown
🔴 [blocking] "The Domain entity imports a database connection directly, violating the dependency rule"
🟡 [important] "The Controller contains business calculations; move them to the Service layer"
💡 [suggestion] "Consider dependency injection to decouple these components"
```

---

## Evaluating Design Pattern Use

### When to Use a Design Pattern

| Pattern | Good fit | Poor fit |
|------|----------|------------|
| **Factory** | Need to create objects of different types, decided at runtime | Only one type, or the type never changes |
| **Strategy** | Algorithm must switch at runtime; several interchangeable behaviors | Only one algorithm, or it never changes |
| **Observer** | One-to-many dependency; state changes must notify several objects | A simple direct call is enough |
| **Singleton** | A single global instance is truly required, e.g. config management | Objects that can be passed via dependency injection |
| **Decorator** | Responsibilities must be added dynamically, avoiding inheritance explosion | Fixed responsibilities, no dynamic composition needed |

### Over-Engineering Warning Signs

```
⚠️ Signs of Patternitis:

1. A simple if/else replaced with Strategy + Factory + Registry
2. Interface with only one implementation that is not at an external boundary (DB / HTTP / third-party service)
3. Abstraction layers added "in case we need them later"
4. Line count grows sharply because of applied patterns
5. Newcomers need a long time to understand the code structure
```

### Review Principles

```markdown
✅ Patterns used well:
- Solve a real extensibility problem
- Make code easier to understand and test
- Make adding features simpler

❌ Patterns overused:
- Used for the sake of using a pattern
- Add unnecessary complexity
- Violate YAGNI
```

### Review Questions

- "What concrete problem does this pattern solve?"
- "Without this pattern, what would go wrong with the code?"
- "Is the value of this abstraction layer greater than its complexity?"

---

## Assessing Extensibility

### Extensibility Checklist

**Feature extensibility:**
- [ ] Does adding a feature require changing core code?
- [ ] Are extension points provided (hooks, plugins, events)?
- [ ] Is configuration externalized (config files, environment variables)?

**Data extensibility:**
- [ ] Does the data model support adding fields?
- [ ] Has data volume growth been considered?
- [ ] Do queries have appropriate indexes?

**Load scalability:**
- [ ] Can it scale horizontally (add more instances)?
- [ ] Are there state dependencies (session, local cache)?
- [ ] Does the database use a connection pool?

### Extension Point Design Check

```typescript
// ✅ Good extension design: events/hooks
class OrderService {
  private hooks: OrderHooks;

  async createOrder(order: Order) {
    await this.hooks.beforeCreate?.(order);
    const result = await this.save(order);
    await this.hooks.afterCreate?.(result);
    return result;
  }
}

// ❌ Poor extension design: all behavior hardcoded
class OrderService {
  async createOrder(order: Order) {
    await this.sendEmail(order);        // hardcoded
    await this.updateInventory(order);  // hardcoded
    await this.notifyWarehouse(order);  // hardcoded
    return await this.save(order);
  }
}
```

### Review Comments

```markdown
💡 [suggestion] "If we need to support a new payment method later, is this design easy to extend?"
🟡 [important] "This logic is hardcoded; consider configuration or the Strategy pattern?"
📚 [learning] "An event-driven architecture would make this feature easier to extend"
```

---

## Code Structure Best Practices

### Directory Organization

**Organize by feature/domain (recommended):**
```
src/
├── user/
│   ├── User.ts           (entity)
│   ├── UserService.ts    (service)
│   ├── UserRepository.ts (data access)
│   └── UserController.ts (API)
├── order/
│   ├── Order.ts
│   ├── OrderService.ts
│   └── ...
└── shared/
    ├── utils/
    └── types/
```

**Organize by technical layer (not recommended):**
```
src/
├── controllers/     ← different domains mixed together
│   ├── UserController.ts
│   └── OrderController.ts
├── services/
├── repositories/
└── models/
```

### Naming Convention Check

| Kind | Convention | Example |
|------|------|------|
| Class name | PascalCase, noun | `UserService`, `OrderRepository` |
| Method name | camelCase, verb | `createUser`, `findOrderById` |
| Interface name | I prefix or no prefix | `IUserService` or `UserService` |
| Constant | UPPER_SNAKE_CASE | `MAX_RETRY_COUNT` |
| Private field | Underscore prefix or none | `_cache` or `#cache` |

### File Size Guidelines

```yaml
Suggested limits:
  single file: < 300 lines
  single function: < 50 lines
  single class: < 200 lines
  function parameters: < 4
  nesting depth: < 4 levels

When exceeded:
  - Consider splitting into smaller units
  - Prefer composition over inheritance
  - Extract helper functions or classes
```

### Review Comments

```markdown
🟢 [nit] "This 500-line file could be split by responsibility"
🟡 [important] "Organize directories by feature domain rather than technical layer"
💡 [suggestion] "The function name `process` is vague; rename it to `calculateOrderTotal`?"
```

---

## Quick Reference Checklist

### 5-Minute Architecture Review

```markdown
□ Is the dependency direction correct? (outer layers depend on inner)
□ Are there circular dependencies?
□ Is core business logic decoupled from framework/UI/database?
□ Are SOLID principles followed?
□ Are there obvious anti-patterns?
```

### Red Flags (must fix when introduced by this change; pre-existing issues outside the diff are marked `pre-existing`, capped at 🟡)

```markdown
🔴 Circular dependency - A → B → C → A
🔴 Domain layer contains framework dependencies
🔴 Hardcoded secrets or credentials
```

### Yellow Flags (should fix)

```markdown
🟡 God Object - a single class over 1000 lines (size is a hint, not proof; escalate to 🔴 only when it demonstrably mixes unrelated responsibilities)
🟡 Hardcoded configuration that varies by environment (non-secret values are not blocking)
🟡 Coupling Between Objects (CBO) > 10
🟡 More than 5 method parameters
🟡 Nesting deeper than 4 levels
🟡 Duplicated code blocks > 10 lines
🟡 Interface with only one implementation that is not at an external boundary (DB / HTTP / third-party service)
🟡 External service calls scattered through business logic with no injection point / adapter, so they cannot be substituted in tests
```

---

## Recommended Tools

| Tool | Purpose | Language support |
|------|------|----------|
| **SonarQube** | Code quality, coupling analysis | Multi-language |
| **NDepend** | Dependency analysis, architecture rules | .NET |
| **JDepend** | Package dependency analysis | Java |
| **Madge** | Module dependency graph | JavaScript/TypeScript |
| **ESLint** | Code style, complexity checks | JavaScript/TypeScript |
| **CodeScene** | Technical debt, hotspot analysis | Multi-language |

---

## References

- [Clean Architecture - Uncle Bob](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)
- [SOLID Principles in Code Review - JetBrains](https://blog.jetbrains.com/upsource/2015/08/31/what-to-look-for-in-a-code-review-solid-principles-2/)
- [Software Architecture Anti-Patterns](https://medium.com/@christophnissle/anti-patterns-in-software-architecture-3c8970c9c4f5)
- [Coupling and Cohesion in System Design](https://www.geeksforgeeks.org/system-design/coupling-and-cohesion-in-system-design/)
- [Design Patterns - Refactoring Guru](https://refactoring.guru/design-patterns)
