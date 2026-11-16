# The N+1 Query Problem — Cross-Language Guide

> N+1 queries are the most common performance anti-pattern in ORMs and database access layers. This document covers the problem definition, detection methods, general solutions and cross-language code examples.

## Table of Contents

- [Problem Definition](#problem-definition)
- [Performance Impact](#performance-impact)
- [Detection Methods](#detection-methods)
- [General Solutions](#general-solutions)
- [Language-Specific Implementations](#language-specific-implementations)
- [Review Checklist](#review-checklist)

---

## Problem Definition

An N+1 query means: **1 query fetches N records, then N extra queries are triggered in a loop** to fetch related data.

```
Request flow:
  1 query   → fetch N parent records
  N queries → one query per parent record for related data
  ─────────
  Total: 1 + N queries
```

### Why It Hurts

| Problem | Impact |
|------|------|
| **Query count grows linearly** | 100 records = 101 SQL queries, 1000 = 1001 |
| **Network latency adds up** | Every query has a round-trip time (RTT); N round trips >> 1 batch query |
| **Connection pool exhaustion** | Many queries tie up DB connections and slow down the whole application |
| **Hard to spot in development** | Little data in dev hides N+1; performance collapses with production data volumes |

---

## Performance Impact

### Scenario Comparison: Fetching 100 Users and Their Orders

| Approach | SQL Count | Latency (assuming RTT=1ms) | Use Case |
|------|----------|---------------------|---------|
| N+1 lazy loading | 101 | ~101ms | Very small data volumes |
| Eager loading (JOIN) | 1 | ~1ms | One-to-many, moderate data volume |
| Eager loading (IN) | 2 | ~2ms | Many-to-many, large datasets |
| DataLoader / batch | 2 | ~2ms | GraphQL / complex graph queries |

### SQL Count Comparison

```sql
-- ❌ N+1: 1 + 100 = 101 queries
SELECT * FROM users;                          -- 1 query
SELECT * FROM orders WHERE user_id = 1;       -- query 2
SELECT * FROM orders WHERE user_id = 2;       -- query 3
...
SELECT * FROM orders WHERE user_id = 100;     -- query 101

-- ✅ Batch: 2 queries
SELECT * FROM users;
SELECT * FROM orders WHERE user_id IN (1,2,...,100);
```

---

## Detection Methods

### 1. ORM SQL Logging

Enable SQL logging and watch the query count in test or development environments:

```python
# Django
import logging
logging.getLogger('django.db.backends').setLevel(logging.DEBUG)

# SQLAlchemy
import logging
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
```

```yaml
# Spring Boot application.yml
spring:
  jpa:
    show-sql: true
    properties:
      hibernate.format_sql: true
```

```csharp
// EF Core
optionsBuilder.LogTo(Console.WriteLine, LogLevel.Information);
```

### 2. Query Count Assertions

Assert the number of SQL queries in tests:

```python
# Django: count queries with CaptureQueriesContext (or assertNumQueries in TestCase)
from django.test.utils import CaptureQueriesContext
from django.db import connection

with CaptureQueriesContext(connection) as ctx:
    list(User.objects.select_related("profile").all())
assert len(ctx) <= 2  # expect at most 2 queries
```

```java
// Hibernate: p6spy or datasource-proxy
// count SQL executions in tests
assertThat(sqlCount).isLessThanOrEqualTo(2);
```

### 3. APM / Database Monitoring Tools

- **Django Debug Toolbar** — shows SQL count and timing in real time
- **p6spy** (Java) — intercepts at the JDBC layer, logs all SQL
- **MiniProfiler** (.NET) — in-page SQL statistics
- **DataDog / New Relic** — slow query alerts in production

---

## General Solutions

### Solution 1: Eager Loading (JOIN Preloading)

A single JOIN query fetches the parent and related records. Suited to one-to-one and one-to-many.

### Solution 2: Batch Fetching (IN-Clause Batch Queries)

Two queries: parent records + `WHERE id IN (...)` to fetch related records in bulk. Suited to many-to-many and large datasets.

### Solution 3: DataLoader Pattern

In GraphQL or complex graph query scenarios, collect all the needed IDs and merge them into a single batch query.

```
// DataLoader pseudocode
class DataLoader<K, V> {
    load(K key) → V         // registers the need, doesn't query immediately
    loadAll([K]) → [V]      // merged into a single batch query
}
```

### Solution 4: Projection

Query only the fields you need to reduce data transfer:

```sql
-- ❌ Fetches all columns
SELECT * FROM users JOIN profiles ON ...

-- ✅ Project only the needed fields
SELECT u.name, p.avatar_url FROM users u JOIN profiles p ON ...
```

---

## Language-Specific Implementations

### Python / Django

> See [Django Guide](../django.md#n1-查询优化)

```python
# ForeignKey / OneToOne → select_related (SQL JOIN)
books = Book.objects.select_related("publisher")

# M2M / reverse FK → prefetch_related (2 queries + Python merge)
authors = Author.objects.prefetch_related("books")

# Nested prefetching
authors = Author.objects.prefetch_related("books__publisher")

# Fine-grained control with Prefetch objects
from django.db.models import Prefetch
authors = Author.objects.prefetch_related(
    Prefetch("books", queryset=Book.objects.filter(published=True), to_attr="published_books")
)
```

### Python / SQLAlchemy (FastAPI)

> See [FastAPI Guide](../fastapi.md#database-sessions--n1)

```python
from sqlalchemy.orm import joinedload, selectinload

# selectinload: IN-clause batch loading (recommended for async)
stmt = select(Order).options(selectinload(Order.customer))

# joinedload: JOIN loading
stmt = select(Order).options(joinedload(Order.customer))
```

### Java / JPA (Spring Boot)

> See [Java Guide](../java.md)

```java
// ❌ FetchType.EAGER or lazy loading triggered in a loop
@OneToMany(fetch = FetchType.EAGER)  // Dangerous!

// ✅ JOIN FETCH
@Query("SELECT u FROM User u JOIN FETCH u.orders")
List<User> findAllWithOrders();

// ✅ @EntityGraph (declarative)
@EntityGraph(attributePaths = {"orders", "profile"})
List<User> findAll();

// ✅ @BatchSize (reduces N+1 to N/batchSize + 1)
@OneToMany
@BatchSize(size = 50)
private List<Order> orders;
```

### C# / EF Core

> See [C# Guide](../csharp.md)

```csharp
// ❌ N+1: foreach triggers lazy loading
foreach (var blog in await context.Blogs.ToListAsync())
    foreach (var post in blog.Posts)  // queries on every iteration!

// ✅ Include + ThenInclude
var blogs = await context.Blogs
    .Include(b => b.Posts)
    .ToListAsync();

// ✅ Projection (safest, avoids over-fetching)
var data = await context.Blogs
    .Select(b => new { b.Url, PostTitles = b.Posts.Select(p => p.Title) })
    .ToListAsync();
```

### PHP / Laravel / Doctrine

> See [PHP Guide](../php.md)

```php
// ❌ Query inside a loop
foreach ($orders as $order) {
    $customer = $customerRepo->find($order->customerId);
    render($order, $customer);
}

// ✅ Batch preloading
$customerIds = array_unique(array_map(fn($o) => $o->customerId, $orders));
$customers = $customerRepo->findByIds($customerIds);

foreach ($orders as $order) {
    render($order, $customers[$order->customerId] ?? null);
}

// Laravel Eloquent: with()
$orders = Order::with('customer')->get();

// Doctrine: JOIN FETCH
$dql = 'SELECT o, c FROM Order o JOIN o.customer c';
```

### TypeScript / Prisma

```typescript
// ❌ N+1
const users = await prisma.user.findMany();
for (const user of users) {
    const posts = await prisma.post.findMany({ where: { userId: user.id } });  // one query per user
}

// ✅ include (Prisma generates a JOIN or batch queries automatically)
const users = await prisma.user.findMany({
    include: { posts: true },
});

// ✅ Nested include
const users = await prisma.user.findMany({
    include: {
        posts: {
            include: { comments: true },
        },
    },
});
```

---

## Review Checklist

### Detection
- [ ] SQL logging or query count monitoring is enabled
- [ ] Tests include query count assertions
- [ ] APM tooling is configured with N+1 alerts

### Fixes
- [ ] ForeignKey / OneToOne relations use JOIN eager loading
- [ ] M2M / reverse relations use IN batch preloading
- [ ] No database queries triggered inside loops
- [ ] Projection is used to fetch only the needed fields

### Architecture
- [ ] List APIs are paginated to avoid loading too many records at once
- [ ] DataLoader is used in GraphQL scenarios
- [ ] A caching strategy (Redis) handles frequently read related data
