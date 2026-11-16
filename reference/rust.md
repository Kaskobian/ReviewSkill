# Rust Code Review Guide

> Rust code review guide. The compiler catches memory-safety issues, but reviewers must focus on what it cannot detect: business logic, API design, performance, cancellation safety and maintainability.

## Contents

- [Ownership and Borrowing](#ownership-and-borrowing)
- [Unsafe Code Review](#unsafe-code-review-most-critical)
- [Async Code](#async-code)
- [Cancellation Safety](#cancellation-safety)
- [spawn vs await](#spawn-vs-await)
- [Error Handling](#error-handling)
- [Performance](#performance)
- [Trait Design](#trait-design)
- [Review Checklist](#rust-review-checklist)

---

## Ownership and Borrowing

### Avoid Unnecessary clone()

```rust
// ❌ clone() is "Rust's duct tape" — used to get around the borrow checker
fn bad_process(data: &Data) -> Result<()> {
    let owned = data.clone();  // why is a clone needed?
    expensive_operation(owned)
}

// ✅ Ask in review: is the clone necessary? Can a borrow do?
fn good_process(data: &Data) -> Result<()> {
    expensive_operation(data)  // pass a reference
}

// ✅ If a clone really is needed, add a comment explaining why
fn justified_clone(data: &Data) -> Result<()> {
    // Clone needed: data will be moved to spawned task
    let owned = data.clone();
    tokio::spawn(async move {
        process(owned).await
    });
    Ok(())
}
```

### Using Arc<Mutex<T>>

```rust
// ❌ Arc<Mutex<T>> can hide unnecessary shared state
struct BadService {
    cache: Arc<Mutex<HashMap<String, Data>>>,  // does it really need sharing?
}

// ✅ Consider whether sharing is needed, or whether the design can avoid it
struct GoodService {
    cache: HashMap<String, Data>,  // single owner
}

// ✅ If concurrent access really is needed, consider a better data structure
use dashmap::DashMap;

struct ConcurrentService {
    cache: DashMap<String, Data>,  // finer-grained locking
}
```

### Cow (Copy-on-Write) Pattern

```rust
use std::borrow::Cow;

// ❌ Always allocates a new string
fn bad_process_name(name: &str) -> String {
    if name.is_empty() {
        "Unknown".to_string()  // allocates
    } else {
        name.to_string()  // unnecessary allocation
    }
}

// ✅ Use Cow to avoid unnecessary allocation
fn good_process_name(name: &str) -> Cow<'_, str> {
    if name.is_empty() {
        Cow::Borrowed("Unknown")  // static string, no allocation
    } else {
        Cow::Borrowed(name)  // borrow the original data
    }
}

// ✅ Allocate only when modification is needed
fn normalize_name(name: &str) -> Cow<'_, str> {
    if name.chars().any(|c| c.is_uppercase()) {
        Cow::Owned(name.to_lowercase())  // needs modification, allocates
    } else {
        Cow::Borrowed(name)  // no modification needed, borrow
    }
}
```

---

## Unsafe Code Review (Most Critical!)

### Basic Requirements

```rust
// ❌ unsafe without safety docs — this is a red flag
unsafe fn bad_transmute(bytes: [u8; 4]) -> f32 {
    std::mem::transmute(bytes)
}

// ✅ Every unsafe must explain: why is it safe? Which invariants?
/// Transmutes `T` to `U`.
///
/// # Safety
///
/// - `T` and `U` must have the same size
/// - the bits of `t` must be a valid value of `U`
unsafe fn documented_transmute<T, U>(t: T) -> U {
    assert_eq!(std::mem::size_of::<T>(), std::mem::size_of::<U>());
    let t = std::mem::ManuallyDrop::new(t);
    // SAFETY: sizes are equal (checked above); caller guarantees bit validity.
    // (`transmute` itself is rejected between unconstrained generic types: E0512.)
    unsafe { std::mem::transmute_copy::<T, U>(&*t) }
}
```

### Unsafe Block Comments

```rust
// ❌ unsafe block with no explanation
fn bad_get_unchecked(slice: &[u8], index: usize) -> u8 {
    unsafe { *slice.get_unchecked(index) }
}

// ✅ Every unsafe block needs a SAFETY comment; when the caller must uphold the precondition, the function itself must be an unsafe fn
// (debug_assert! is removed in release builds, so it cannot serve as the bounds check of a safe fn)
/// # Safety
/// `index` must be less than `slice.len()`.
unsafe fn good_get_unchecked(slice: &[u8], index: usize) -> u8 {
    debug_assert!(index < slice.len(), "index out of bounds");
    // SAFETY: the caller guarantees index < slice.len().
    unsafe { *slice.get_unchecked(index) }
}

// ✅ Wrap unsafe behind a safe API
pub fn checked_get(slice: &[u8], index: usize) -> Option<u8> {
    if index < slice.len() {
        // SAFETY: bounds check performed above
        Some(unsafe { *slice.get_unchecked(index) })
    } else {
        None
    }
}
```

### Common unsafe Patterns

```rust
// ✅ FFI boundary
unsafe extern "C" {
    fn external_function(ptr: *const u8, len: usize) -> i32;
}

pub fn safe_wrapper(data: &[u8]) -> Result<i32, Error> {
    // SAFETY: data.as_ptr() is valid for data.len() bytes,
    // and external_function only reads from the buffer.
    let result = unsafe {
        external_function(data.as_ptr(), data.len())
    };
    if result < 0 {
        Err(Error::from_code(result))
    } else {
        Ok(result)
    }
}

// ✅ unsafe on a performance-critical path
pub fn fast_copy(src: &[u8], dst: &mut [u8]) {
    assert_eq!(src.len(), dst.len(), "slices must be equal length");
    // SAFETY: src and dst are valid slices of equal length,
    // and dst is mutable so no aliasing.
    unsafe {
        std::ptr::copy_nonoverlapping(
            src.as_ptr(),
            dst.as_mut_ptr(),
            src.len()
        );
    }
}
```

---

## Async Code

> 📖 For general concurrency patterns and cross-language examples, see the [Async and Concurrency Cross-Language Guide](cross-cutting/async-concurrency-patterns.md)

### Avoid Blocking Operations

```rust
// ❌ Blocking in an async context — starves other tasks
async fn bad_async() {
    let data = std::fs::read_to_string("file.txt").unwrap();  // blocks!
    std::thread::sleep(Duration::from_secs(1));  // blocks!
}

// ✅ Use async APIs
async fn good_async() -> Result<String> {
    let data = tokio::fs::read_to_string("file.txt").await?;
    tokio::time::sleep(Duration::from_secs(1)).await;
    Ok(data)
}

// ✅ If a blocking operation is unavoidable, use spawn_blocking
async fn with_blocking() -> Result<Data> {
    let result = tokio::task::spawn_blocking(|| {
        // blocking operations are safe here
        expensive_cpu_computation()
    }).await?;
    Ok(result)
}
```

### Mutex and .await

```rust
// ❌ Holding a std::sync::Mutex across .await — can deadlock
async fn bad_lock(mutex: &std::sync::Mutex<Data>) {
    let guard = mutex.lock().unwrap();
    async_operation().await;  // waiting while holding the lock!
    process(&guard);
}

// ✅ Option 1: minimize the lock scope
async fn good_lock_scoped(mutex: &std::sync::Mutex<Data>) {
    let data = {
        let guard = mutex.lock().unwrap();
        guard.clone()  // release the lock immediately
    };
    async_operation().await;
    process(&data);
}

// ✅ Option 2: use tokio::sync::Mutex (can be held across await)
async fn good_lock_tokio(mutex: &tokio::sync::Mutex<Data>) {
    let guard = mutex.lock().await;
    async_operation().await;  // OK: tokio Mutex is designed to be held across await
    process(&guard);
}

// 💡 How to choose:
// - std::sync::Mutex: low contention, short critical sections, not held across await
// - tokio::sync::Mutex: only when the lock must be held across .await (higher overhead)
// - High contention: sharded locks, a dedicated task + channel, or refactor to avoid the shared lock — not a switch to tokio Mutex
```

### Async Trait Methods

```rust
// ❌ Pitfall of async trait methods (older versions)
#[async_trait]
trait BadRepository {
    async fn find(&self, id: i64) -> Option<Entity>;  // implicit Box
}

// ✅ Rust 1.75+: native async trait methods
trait Repository {
    async fn find(&self, id: i64) -> Option<Entity>;

    // return a concrete Future type to avoid allocation
    fn find_many(&self, ids: &[i64]) -> impl Future<Output = Vec<Entity>> + Send;
}

// ✅ For cases that need dyn
trait DynRepository: Send + Sync {
    fn find(&self, id: i64) -> Pin<Box<dyn Future<Output = Option<Entity>> + Send + '_>>;
}
```

---

## Cancellation Safety

### What Cancellation Safety Means

```rust
// When a Future is dropped at an .await point, what state is it left in?
// Cancel-safe Future: can be cancelled safely at any await point
// Cancel-unsafe Future: cancellation may cause data loss or inconsistent state

// ❌ Cancel-unsafe example
async fn cancel_unsafe(conn: &mut Connection) -> Result<()> {
    let data = receive_data().await;  // if cancelled here...
    conn.send_ack().await;  // ...the ack is never sent and data may be lost
    Ok(())
}

// ✅ Cancel-safe version
async fn cancel_safe(conn: &mut Connection) -> Result<()> {
    // use a transaction or atomic operation to ensure consistency
    let transaction = conn.begin_transaction().await?;
    let data = receive_data().await;
    transaction.commit_with_ack(data).await?;  // atomic operation
    Ok(())
}
```

### Cancellation Safety in select!

```rust
use tokio::select;

// ❌ Using a cancel-unsafe Future in select!
async fn bad_select(stream: &mut TcpStream) {
    let mut buffer = vec![0u8; 1024];
    loop {
        select! {
            // read_exact is not cancel safe: when the timeout fires first,
            // bytes already read into buffer are dropped together with the Future
            result = stream.read_exact(&mut buffer) => {
                result?;
                handle_data(&buffer);
            }
            _ = tokio::time::sleep(Duration::from_secs(5)) => {
                println!("Timeout");
            }
        }
    }
}

// ✅ Use cancel-safe APIs
async fn good_select(stream: &mut TcpStream) -> io::Result<()> {
    let mut buffer = vec![0u8; 1024];
    loop {
        select! {
            // read is cancel safe: on cancellation, unread data stays in the stream
            // if you really need fixed-length reads, move read_exact into a separate task
            // and select! on its JoinHandle here, so cancellation loses no bytes
            result = stream.read(&mut buffer) => {
                match result {
                    Ok(0) => break,  // EOF
                    Ok(n) => handle_data(&buffer[..n]),
                    Err(e) => return Err(e),
                }
            }
            _ = tokio::time::sleep(Duration::from_secs(5)) => {
                println!("Timeout, retrying...");
            }
        }
    }
    Ok(())
}

// ✅ Use tokio::pin! so the Future can be reused safely
async fn pinned_select() {
    let sleep = tokio::time::sleep(Duration::from_secs(10));
    tokio::pin!(sleep);

    loop {
        select! {
            _ = &mut sleep => {
                println!("Timer elapsed");
                break;
            }
            data = receive_data() => {
                process(data).await;
                // sleep keeps counting down and is not reset
            }
        }
    }
}
```

### Documenting Cancellation Safety

```rust
/// Reads a complete message from the stream.
///
/// # Cancel Safety
///
/// This method is **not** cancel safe. If cancelled while reading,
/// partial data may be lost and the stream state becomes undefined.
/// Use `read_message_cancel_safe` if cancellation is expected.
async fn read_message(stream: &mut TcpStream) -> Result<Message> {
    let len = stream.read_u32().await?;
    let mut buffer = vec![0u8; len as usize];
    stream.read_exact(&mut buffer).await?;
    Ok(Message::from_bytes(&buffer))
}

/// Reads a message with cancel safety.
///
/// # Cancel Safety
///
/// This method is cancel safe. If cancelled, any partial data
/// is preserved in the internal buffer for the next call.
async fn read_message_cancel_safe(reader: &mut BufferedReader) -> Result<Message> {
    reader.read_message_buffered().await
}
```

---

## spawn vs await

### When to Use spawn

```rust
// ❌ Unnecessary spawn — adds overhead and loses structured concurrency
async fn bad_unnecessary_spawn() {
    let handle = tokio::spawn(async {
        simple_operation().await
    });
    handle.await.unwrap();  // why not just await directly?
}

// ✅ Await simple operations directly
async fn good_direct_await() {
    simple_operation().await;
}

// ✅ Use spawn for real parallel execution
async fn good_parallel_spawn() -> Result<(), tokio::task::JoinError> {
    let task1 = tokio::spawn(fetch_from_service_a());
    let task2 = tokio::spawn(fetch_from_service_b());

    // both requests run in parallel
    let (result1, result2) = tokio::try_join!(task1, task2)?;
    Ok(())
}

// ✅ Use spawn for background tasks (fire-and-forget)
async fn good_background_spawn() {
    // start a background task without waiting for it
    tokio::spawn(async {
        cleanup_old_sessions().await;
        log_metrics().await;
    });

    // continue with other work
    handle_request().await;
}
```

### The 'static Requirement of spawn

```rust
// ❌ A spawned Future must be 'static
async fn bad_spawn_borrow(data: &Data) {
    tokio::spawn(async {
        process(data).await;  // Error: `data` is not 'static
    });
}

// ✅ Option 1: clone the data
async fn good_spawn_clone(data: &Data) {
    let owned = data.clone();
    tokio::spawn(async move {
        process(&owned).await;
    });
}

// ✅ Option 2: share via Arc
async fn good_spawn_arc(data: Arc<Data>) {
    let data = Arc::clone(&data);
    tokio::spawn(async move {
        process(&data).await;
    });
}

// ✅ Option 3: run concurrently in the current task (no spawn, so borrowing works)
async fn good_borrowing_concurrency(data: &Data) {
    tokio::join!(process(data), process(data));
}
// Note: async-scoped has no free `scope` fn; its safe `TokioScope::scope_and_block` blocks the thread, and the awaitable `scope_and_collect` is `unsafe`.
```

### JoinHandle Error Handling

```rust
// ❌ Ignoring errors from spawn
async fn bad_ignore_spawn_error() {
    let handle = tokio::spawn(async {
        risky_operation().await
    });
    let _ = handle.await;  // ignores panics and errors
}

// ✅ Handle the JoinHandle result properly
async fn good_handle_spawn_error() -> Result<()> {
    let handle = tokio::spawn(async {
        risky_operation().await
    });

    match handle.await {
        Ok(Ok(result)) => {
            // task completed successfully
            process_result(result);
            Ok(())
        }
        Ok(Err(e)) => {
            // error inside the task
            Err(e.into())
        }
        Err(join_err) => {
            // task panicked or was cancelled
            if join_err.is_panic() {
                error!("Task panicked: {:?}", join_err);
            }
            Err(anyhow!("Task failed: {}", join_err))
        }
    }
}
```

### Structured Concurrency vs spawn

```rust
// ✅ Prefer join! (structured concurrency)
async fn structured_concurrency() -> Result<(A, B, C)> {
    // all tasks live in the same scope
    // if any one fails, the others are cancelled
    tokio::try_join!(
        fetch_a(),
        fetch_b(),
        fetch_c()
    )
}

// ✅ When using spawn, think about task lifetimes
struct TaskManager {
    handles: Vec<JoinHandle<()>>,
}

impl TaskManager {
    async fn shutdown(self) {
        // graceful shutdown: wait for all tasks to finish
        for handle in self.handles {
            if let Err(e) = handle.await {
                error!("Task failed during shutdown: {}", e);
            }
        }
    }

    async fn abort_all(self) {
        // forced shutdown: cancel all tasks
        for handle in self.handles {
            handle.abort();
        }
    }
}
```

---

## Error Handling

> 📖 For general principles and cross-language examples, see the [Error Handling Cross-Language Guide](cross-cutting/error-handling-principles.md)

### Error Types: Library vs Application

```rust
// ❌ anyhow in library code — callers cannot match on errors
pub fn parse_config(s: &str) -> anyhow::Result<Config> { ... }

// ✅ thiserror for libraries, anyhow for applications
#[derive(Debug, thiserror::Error)]
pub enum ConfigError {
    #[error("invalid syntax at line {line}: {message}")]
    Syntax { line: usize, message: String },
    #[error("missing required field: {0}")]
    MissingField(String),
    #[error(transparent)]
    Io(#[from] std::io::Error),
}

pub fn parse_config(s: &str) -> Result<Config, ConfigError> { ... }
```

### Preserve Error Context

```rust
// ❌ Swallowing error context
fn bad_error() -> Result<()> {
    operation().map_err(|_| anyhow!("failed"))?;  // original error lost
    Ok(())
}

// ✅ Use context to keep the error chain
fn good_error() -> Result<()> {
    operation().context("failed to perform operation")?;
    Ok(())
}

// ✅ Use with_context for lazy evaluation
fn good_error_lazy() -> Result<()> {
    operation()
        .with_context(|| format!("failed to process file: {}", filename))?;
    Ok(())
}
```

### Error Type Design

```rust
// ✅ Use #[source] to keep the error chain
#[derive(Debug, thiserror::Error)]
pub enum ServiceError {
    #[error("database error")]
    Database(#[source] sqlx::Error),

    #[error("network error: {message}")]
    Network {
        message: String,
        #[source]
        source: reqwest::Error,
    },

    #[error("validation failed: {0}")]
    Validation(String),
}

// ✅ Implement From for common conversions
impl From<sqlx::Error> for ServiceError {
    fn from(err: sqlx::Error) -> Self {
        ServiceError::Database(err)
    }
}
```

---

## Performance

### Avoid Unnecessary collect()

```rust
// ❌ Unnecessary collect — intermediate allocation
fn bad_sum(items: &[i32]) -> i32 {
    items.iter()
        .filter(|x| **x > 0)
        .collect::<Vec<_>>()  // unnecessary!
        .iter()
        .sum()
}

// ✅ Lazy iteration
fn good_sum(items: &[i32]) -> i32 {
    items.iter().filter(|x| **x > 0).copied().sum()
}
```

### String Concatenation

```rust
// ❌ Each iteration creates a new String and copies all existing content (O(n²))
fn bad_concat(items: &[&str]) -> String {
    let mut s = String::new();
    for item in items {
        s = format!("{}{}", s, item);  // note: `s = s + item` reuses s's buffer and does not have this problem
    }
    s
}

// ✅ Preallocate or use join
fn good_concat(items: &[&str]) -> String {
    items.join("")
}

// ✅ Preallocate with with_capacity
fn good_concat_capacity(items: &[&str]) -> String {
    let total_len: usize = items.iter().map(|s| s.len()).sum();
    let mut result = String::with_capacity(total_len);
    for item in items {
        result.push_str(item);
    }
    result
}

// ✅ Use the write! macro
use std::fmt::Write;

fn good_concat_write(items: &[&str]) -> String {
    let mut result = String::new();
    for item in items {
        write!(result, "{}", item).unwrap();
    }
    result
}
```

### Avoid Unnecessary Allocation

```rust
// ❌ Unnecessary Vec allocation
fn bad_check_any(items: &[Item]) -> bool {
    let filtered: Vec<_> = items.iter()
        .filter(|i| i.is_valid())
        .collect();
    !filtered.is_empty()
}

// ✅ Use iterator methods
fn good_check_any(items: &[Item]) -> bool {
    items.iter().any(|i| i.is_valid())
}

// ❌ String::from for a static string
fn bad_static() -> String {
    String::from("error message")  // runtime allocation
}

// ✅ Return &'static str
fn good_static() -> &'static str {
    "error message"  // no allocation
}
```

---

## Trait Design

### Avoid Over-Abstraction

```rust
// ❌ Over-abstraction — this is not Java, not everything needs an Interface
trait Processor { fn process(&self); }
trait Handler { fn handle(&self); }
trait Manager { fn manage(&self); }  // too many traits

// ✅ Create a trait only when you need polymorphism
// concrete types are usually simpler and faster
struct DataProcessor {
    config: Config,
}

impl DataProcessor {
    fn process(&self, data: &Data) -> Result<Output> {
        // implement directly
    }
}
```

### Trait Objects vs Generics

```rust
// ❌ Unnecessary trait object (dynamic dispatch)
fn bad_process(handler: &dyn Handler) {
    handler.handle();  // vtable call
}

// ✅ Use generics (static dispatch, inlinable)
fn good_process<H: Handler>(handler: &H) {
    handler.handle();  // may be inlined
}

// ✅ Where trait objects fit: heterogeneous collections
fn store_handlers(handlers: Vec<Box<dyn Handler>>) {
    // need to store handlers of different types
}

// ✅ Use impl Trait as the return type
fn create_handler() -> impl Handler {
    ConcreteHandler::new()
}
```

---

## Rust Review Checklist

### Issues the Compiler Cannot Catch

**Business logic correctness**
- [ ] Edge cases handled correctly
- [ ] State machine transitions complete
- [ ] Race conditions under concurrency

**API design**
- [ ] Public API is hard to misuse
- [ ] Type signatures express intent clearly
- [ ] Error type granularity is appropriate

### Ownership and Borrowing

- [ ] clone() is deliberate and the reason is documented
- [ ] Does Arc<Mutex<T>> really need shared state?
- [ ] RefCell use is justified
- [ ] Lifetimes are not overly complex
- [ ] Consider Cow to avoid unnecessary allocation

### Unsafe Code (Most Important)

- [ ] Every unsafe block has a SAFETY comment
- [ ] unsafe fn has a # Safety doc section
- [ ] Explains why it is safe, not just what it does
- [ ] Lists the invariants that must be upheld
- [ ] unsafe boundary is as small as possible
- [ ] Considered whether a safe alternative exists

### Async/Concurrency

- [ ] No blocking in async (std::fs, thread::sleep)
- [ ] No std::sync locks held across .await
- [ ] Spawned tasks satisfy 'static
- [ ] Locks acquired in a consistent order
- [ ] Channel buffer sizes are reasonable

### Cancellation Safety

- [ ] Futures in select! are cancel safe
- [ ] Cancellation safety of async functions is documented
- [ ] Cancellation cannot cause data loss or inconsistent state
- [ ] tokio::pin! used correctly for Futures that are reused

### spawn vs await

- [ ] spawn only where real parallelism is needed
- [ ] Simple operations are awaited directly, not spawned
- [ ] JoinHandle results of spawn are handled properly
- [ ] Task lifetimes and shutdown strategy considered
- [ ] Prefer join!/try_join! for structured concurrency

### Error Handling

- [ ] Libraries: thiserror for structured errors
- [ ] Applications: anyhow + context
- [ ] No unwrap/expect in production code
- [ ] Error messages help debugging
- [ ] must_use return values are handled
- [ ] #[source] used to keep the error chain

### Performance

- [ ] Avoid unnecessary collect()
- [ ] Pass large data by reference
- [ ] Strings built with with_capacity or write!
- [ ] impl Trait vs Box<dyn Trait> chosen sensibly
- [ ] Avoid allocation on hot paths
- [ ] Consider Cow to reduce cloning

### Code Quality

- [ ] cargo clippy with zero warnings
- [ ] Formatted with cargo fmt
- [ ] Doc comments complete
- [ ] Tests cover edge cases
- [ ] Public API has doc examples
