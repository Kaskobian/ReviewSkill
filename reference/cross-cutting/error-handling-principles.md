# Error Handling Principles — Cross-Language Guide

> This document covers core error handling principles, common anti-patterns, error hierarchy design and logging best practices. Each principle comes with cross-language code examples.

## Table of Contents

- [Core Principles](#core-principles)
- [Anti-Patterns](#anti-patterns)
- [Error Hierarchy Design](#error-hierarchy-design)
- [Logging Best Practices](#logging-best-practices)
- [Cross-Language Code Examples](#cross-language-code-examples)
- [Review Checklist](#review-checklist)

---

## Core Principles

### Principle 1: Don't Swallow Errors

Every error must be handled: propagated upward, logged, or converted into a more meaningful error. **Never** ignore it silently.

```
// Pseudocode
result = risky_operation()
if error:
    // Must do one of the following:
    //   1. return error to caller (propagate)
    //   2. log + return fallback (degrade)
    //   3. panic/crash (when unrecoverable)
```

### Principle 2: Add Context

Error messages should include an **operation description** and **key parameters**, so whoever debugs can locate the problem without reading the call chain.

```
// ❌ No context
"failed"

// ✅ With context
"failed to process order #12345: payment gateway timeout after 30s"
```

### Principle 3: Use Specific Types

Use error types to distinguish failure causes, so callers can handle different failure scenarios precisely.

```
// ❌ Generic error
throw new Error("something went wrong")

// ✅ Specific types
throw new OrderNotFoundError(orderId)
throw new PaymentTimeoutException(gatewayName, timeoutMs)
```

### Principle 4: Fail Fast

Validate preconditions before the operation starts and fail early. This avoids inconsistent state from discovering an error after partial execution.

```
// ❌ Invalid parameter discovered halfway through
def process(data, config):
    result = expensive_computation(data)  # 5 seconds already spent
    if not config.valid:
        raise ValueError("invalid config")  # 5 seconds wasted

// ✅ Validate first
def process(data, config):
    if not config.valid:
        raise ValueError("invalid config")
    result = expensive_computation(data)
```

### Principle 5: Handle Each Error Only Once

Don't handle the same error at every level (log and return and wrap). Pick one approach and let the caller decide how to handle it.

```
// ❌ Both log and return (duplicate handling)
if err:
    log.error("failed: %s", err)
    return err

// ✅ Only wrap and return, let the top level handle it uniformly
if err:
    return wrap_error("operation failed", err)
```

---

## Anti-Patterns

### Anti-Pattern 1: Empty catch Blocks

```python
# ❌ Python: bare except swallows all exceptions (including KeyboardInterrupt)
try:
    result = risky()
except:
    pass

# ❌ Java: empty catch swallows the exception
try {
    result = risky();
} catch (Exception e) {
    // do nothing
}

# ❌ Go: ignoring the error
result, _ := risky()

# ❌ Rust: unwrap() in production code
let result = risky().unwrap();  // panic on error
```

### Anti-Pattern 2: Overly Broad catch

```python
# ❌ Catches all exceptions, can't distinguish failure types
try:
    result = risky()
except Exception as e:
    logger.error(f"failed: {e}")

# ✅ Catch specific exceptions
try:
    result = risky()
except ConnectionError as e:
    logger.warning(f"network issue, retrying: {e}")
    result = retry(risky)
except ValueError as e:
    logger.error(f"bad input: {e}")
    raise
```

### Anti-Pattern 3: Losing the Original Exception

```python
# ❌ The original exception's stack trace and message are lost
try:
    result = external_api.call()
except APIError as e:
    raise RuntimeError("API failed")  # the cause is lost

# ✅ Preserve the exception chain
try:
    result = external_api.call()
except APIError as e:
    raise RuntimeError("API failed") from e
```

```java
// ❌ Loses the original exception
catch (IOException e) {
    throw new ServiceException("IO failed");
}

// ✅ Preserves the cause
catch (IOException e) {
    throw new ServiceException("IO failed", e);
}
```

### Anti-Pattern 4: Exceptions for Control Flow

```python
# ❌ Using an exception to break out of a normal loop (exception as goto)
class Found(Exception): pass
try:
    for item in items:
        if item.matches(q):
            raise Found(item)
except Found as f:
    result = f.args[0]

# ✅ Express the intent directly
result = next((item for item in items if item.matches(q)), None)

# Note: try/except KeyError (EAFP) is idiomatic in Python and should not be flagged.
```

```go
// ❌ Go: panic for control flow
func getUser(id int) User {
    if id <= 0 {
        panic("invalid id")
    }
    return users[id]
}

// ✅ Go: return an error
func getUser(id int) (User, error) {
    if id <= 0 {
        return User{}, fmt.Errorf("invalid user id: %d", id)
    }
    return users[id], nil
}
```

### Anti-Pattern 5: Ignoring Return Values

```csharp
// ❌ Ignores the returned bool/Result
dict.TryGetValue("key", out var value);
// value may be the default, but the code continues as if it succeeded

// ✅ Check the return value
if (!dict.TryGetValue("key", out var value))
{
    throw new KeyNotFoundException("key not found");
}
```

---

## Error Hierarchy Design

### Three-Tier Error Architecture

```
┌─────────────────────────────────────────────────┐
│ Application Errors (application level)          │
│   - AppError / ServiceError                      │
│   - Global handler returns a friendly response  │
├─────────────────────────────────────────────────┤
│ Module Errors (module level)                    │
│   - PaymentError, AuthError, ValidationError     │
│   - Each business module defines its own types  │
├─────────────────────────────────────────────────┤
│ Infrastructure Errors (infrastructure level)    │
│   - IOError, NetworkError, DatabaseError         │
│   - Low-level errors from the OS, network, DB   │
└─────────────────────────────────────────────────┘
```

### Design Rules

1. **Module-level errors inherit from an application-level base class**, making global catching easy
2. **Infrastructure errors are converted to module-level errors at module boundaries**, not exposed to upper layers
3. **Every error type carries enough context** for debugging (ID, timestamp, operation name)

### Example Hierarchy (Python)

```python
class AppError(Exception):
    """Base application exception"""
    pass

class PaymentError(AppError):
    """Payment module error"""
    def __init__(self, order_id: str, reason: str):
        self.order_id = order_id
        super().__init__(f"payment failed for order {order_id}: {reason}")

class PaymentGatewayTimeout(PaymentError):
    """Payment gateway timeout"""
    def __init__(self, order_id: str, gateway: str, timeout_ms: int):
        self.gateway = gateway
        self.timeout_ms = timeout_ms
        super().__init__(order_id, f"gateway {gateway} timed out after {timeout_ms}ms")
```

### Example Hierarchy (Java)

```java
public class AppException extends RuntimeException {
    private final String errorCode;
    public AppException(String errorCode, String message, Throwable cause) {
        super(message, cause);
        this.errorCode = errorCode;
    }
}

public class OrderNotFoundException extends AppException {
    public OrderNotFoundException(Long orderId) {
        super("ORDER_NOT_FOUND", "Order " + orderId + " not found", null);
    }
}
```

---

## Logging Best Practices

### Choosing a Log Level

| Level | When to Use | Examples |
|------|---------|------|
| **ERROR** | Failures that need human intervention | Payment failure, data inconsistency |
| **WARN** | Automatically recoverable issues | Successful retry, degraded handling |
| **INFO** | Normal business events | Order created, user login |
| **DEBUG** | Debugging information | Function arguments, intermediate state |

### Log Format

```
// ❌ No structured information
log.error("failed to process")

// ✅ Structured information + context
log.error("payment_failed", {
    "order_id": "12345",
    "gateway": "stripe",
    "error_code": "card_declined",
    "amount": 99.99,
    "duration_ms": 2340
})
```

### Logging Security

- **Don't log sensitive information**: passwords, tokens, PII, full credit card numbers
- **Masking**: `email: a***@example.com`
- **Log injection protection**: escape user input to prevent forged log lines

---

## Cross-Language Code Examples

### Python

```python
# ✅ Specific exceptions + context + exception chaining
try:
    response = http_client.post(url, data=payload)
    response.raise_for_status()
except requests.ConnectionError as e:
    raise PaymentGatewayError(f"cannot reach {gateway_name}") from e
except requests.HTTPError as e:
    if response.status_code == 429:
        raise RateLimitError(f"rate limited by {gateway_name}") from e
    raise PaymentGatewayError(f"HTTP {response.status_code} from {gateway_name}") from e
```

### Java

```java
// ✅ Specific exceptions + context + cause chaining
try {
    var response = httpClient.send(request, BodyHandlers.ofString());
    if (response.statusCode() == 404) {
        throw new OrderNotFoundException(orderId);
    }
} catch (IOException e) {
    throw new PaymentGatewayException(
        "gateway unreachable: " + gatewayUrl, e);
}
```

### Go

```go
// ✅ Error wrapping + context + %w preserves the chain
result, err := client.Do(req)
if err != nil {
    return fmt.Errorf("payment gateway %s request failed: %w", gatewayName, err)
}
defer result.Body.Close()

if result.StatusCode == http.StatusNotFound {
    return fmt.Errorf("order %d not found: %w", orderID, ErrNotFound)
}
```

### Rust

```rust
// ✅ thiserror defines the error types + context
#[derive(Debug, thiserror::Error)]
enum PaymentError {
    #[error("gateway {gateway} unreachable")]
    GatewayUnreachable {
        gateway: String,
        #[source]
        source: reqwest::Error,
    },
    #[error("order {order_id} not found")]
    OrderNotFound { order_id: u64 },
}

async fn process_payment(gateway: &str, order_id: u64) -> Result<(), PaymentError> {
    let response = client.post(url)
        .send()
        .await
        .map_err(|e| PaymentError::GatewayUnreachable {
            gateway: gateway.into(),
            source: e,
        })?;
    Ok(())
}
```

### C#

```csharp
// ✅ Specific exceptions + context
try
{
    var response = await httpClient.PostAsync(url, content);
    response.EnsureSuccessStatusCode();
}
catch (HttpRequestException ex) when (ex.StatusCode == HttpStatusCode.NotFound)
{
    throw new OrderNotFoundException(orderId, ex);
}
catch (HttpRequestException ex)
{
    throw new PaymentGatewayException($"gateway unreachable: {url}", ex);
}
```

### Swift

```swift
// ✅ Error enum + context
enum PaymentError: Error {
    case gatewayUnreachable(name: String, underlying: Error)
    case orderNotFound(id: Int)
    case declined(reason: String)
}

func processPayment(orderId: Int) throws -> Receipt {
    guard orderId > 0 else {
        throw PaymentError.orderNotFound(id: orderId)
    }
    do {
        let response = try networkClient.post(url, body: payload)
        return try Receipt(from: response)
    } catch let error as NetworkError {
        throw PaymentError.gatewayUnreachable(name: gateway, underlying: error)
    }
}
```

### TypeScript

```typescript
// ✅ Custom error class + context
class PaymentError extends Error {
    constructor(
        message: string,
        public readonly orderId: string,
        public readonly gateway: string,
        cause?: unknown,
    ) {
        super(message, { cause });  // standard Error.cause (ES2022)
        this.name = 'PaymentError';
    }
}

async function processPayment(orderId: string): Promise<Receipt> {
    try {
        const response = await fetch(url, { method: 'POST', body: payload });
        if (!response.ok) {
            throw new PaymentError(
                `gateway returned ${response.status}`,
                orderId,
                gatewayName,
            );
        }
        return await response.json();
    } catch (err) {
        if (err instanceof TypeError) {
            throw new PaymentError('gateway unreachable', orderId, gatewayName, err);
        }
        throw err;
    }
}
```

---

## Review Checklist

### Core Checks
- [ ] No empty catch blocks or silently ignored errors
- [ ] Error messages include an operation description and key parameters
- [ ] Specific error types are used (not generic Error/Exception)
- [ ] Exception chains are preserved (from / cause / %w)
- [ ] Preconditions are validated before the operation starts (fail fast)

### Architecture Checks
- [ ] A clear error hierarchy is defined (application/module/infrastructure)
- [ ] A global exception handler catches unhandled errors
- [ ] API boundaries convert internal errors into appropriate HTTP status codes

### Logging Checks
- [ ] Error logs include structured context
- [ ] No sensitive information is logged (passwords, tokens, PII)
- [ ] Log levels are used correctly (ERROR vs WARN vs INFO)

### Language-Specific
- [ ] Go: errors are not ignored, wrapped with `%w`
- [ ] Python: catch specific exceptions, use `from` to preserve the chain
- [ ] Java: exceptions have a cause, specific types are used
- [ ] Rust: `?` propagation, custom Error types
- [ ] C#: when filters, specific exception types
- [ ] Swift: do-catch, Result for deferred handling
