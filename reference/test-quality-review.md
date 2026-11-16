# Test Quality Review Guide

> Review checklist for the tests in a change: do they assert behavior, would they fail if the logic broke, and will they stay reliable?

A test earns its place by **failing for the right reason**. Coverage numbers, green CI, and tidy structure are all compatible with a suite that catches nothing. Review tests with the same skepticism as the code they cover — especially when both were written by the same author (human or AI) in the same pass.

Severity labels follow the skill standard: 🔴 `[blocking]` · 🟡 `[important]` · 🟢 `[nit]`.

---

## 1. Assertion-Free and Trivial Tests

Tests that execute code but assert nothing (or assert something always true) inflate coverage while verifying nothing.

```javascript
// ❌ Runs the code, asserts nothing — passes whatever parse() returns;
// it only fails if parse() happens to throw
test("parses input", () => {
  parse("a=1;b=2");
});

// ❌ Tautology: asserts the mock returns what the mock was told to return
test("gets user", async () => {
  const mock = jest.fn().mockResolvedValue({ id: 1 });
  expect(await mock()).toEqual({ id: 1 });
});

// ✅ Asserts observable behavior with an independently known answer
test("parses pairs into a map", () => {
  expect(parse("a=1;b=2")).toEqual({ a: "1", b: "2" });
});
```

**Check:**
- [ ] Every test contains at least one assertion on the unit's output or observable side effect
- [ ] No assertion compares a value to itself or to the same expression that produced it
- [ ] `expect(...).resolves` / `does_not_raise` style tests still pin a concrete value where the contract defines one

🔴 A change whose new tests assert nothing has effectively no tests.

---

## 2. Over-Mocking: Testing the Mock

When every collaborator is mocked, the test verifies the wiring of mocks, not the behavior of the system.

```python
# ❌ Mocks the very logic under test — this passes for ANY implementation
def test_calculate_total(mocker):
    mocker.patch("shop.pricing.calculate_total", return_value=90)
    assert shop.pricing.calculate_total(cart) == 90

# ✅ Mock only the boundary (the payment gateway), keep real logic
def test_checkout_charges_total(mocker):
    gateway = mocker.patch("shop.payment.gateway.charge")
    checkout(cart, user)
    gateway.assert_called_once_with(amount=90, currency="USD", user_id=user.id)
```

**Rules of thumb:**
- Mock at **boundaries**: network, database, clock, filesystem, third-party services.
- Keep real: the unit under test, its value objects, and pure helpers.
- If a test needs more than ~2 mocks to exercise one behavior, the design (or the test's target) is wrong — flag the coupling, not just the test.
- A mock's return value must be a realistic fixture, not a convenience that hides edge cases.

🟡 Over-mocked tests are important: they give false confidence and break on refactor.

---

## 3. Implementation-Detail Tests

Tests coupled to *how* the code works break on every harmless refactor and train the team to ignore red CI.

```javascript
// ❌ Asserts an internal helper's call count and private state — breaks when an equivalent refactor lands
expect(spy).toHaveBeenCalledTimes(3);
expect(component.state.internalBuffer).toHaveLength(2);

// ✅ Asserts the public contract
expect(renderedOutput()).toContain("3 items");
```

**Check:**
- [ ] Assertions target public API / rendered output / persisted state, not private fields or call counts of internal collaborators (interaction assertions on a mocked boundary — e.g. the gateway was charged exactly once with the right amount — are observable behavior and are fine)
- [ ] No test reaches into internals (`_private`, `state internals`, reflection) without a stated reason
- [ ] Renaming a private method would not break any test

🟡 Important — brittle suites erode trust in CI.

---

## 4. Flakiness Sources

A test that fails 1% of the time is a tax on every future run. Hunt these in new tests:

| Source | Smell | Fix |
|--------|-------|-----|
| Wall clock | `Date.now()`, `time.time()`, `sleep(2)` | Inject a fake clock / freeze time |
| Randomness | unseeded `random`, UUIDs asserted literally | Seed it, or assert shape not value |
| Ordering | relies on dict/set/DB row order, parallel test interference | Sort before asserting; isolate state |
| Shared state | module-level fixtures mutated across tests | Per-test setup/teardown |
| Network | real HTTP calls, localhost port collisions | Mock the boundary or use ephemeral ports |
| Timing | `sleep` then hope, race between async steps | Await the actual condition/event |

```python
# ❌ Flaky: assumes the background task finishes within 100ms
def test_async_job():
    start_job()
    time.sleep(0.1)
    assert job_done()

# ✅ Deterministic: await the completion signal
def test_async_job():
    handle = start_job()
    handle.wait(timeout=5)  # fails loudly if the contract breaks, not randomly
    assert job_done()
```

🟡 A new flaky test is important — it should be fixed, especially when the fix is cheap (clock injection, seeding); 🔴 blocking when it gates a critical pipeline and fails regularly.

---

## 5. Missing Negative and Edge Cases

Happy-path-only suites are the most common gap, in human and AI code alike.

**For each behavior under test, ask:**
- [ ] Empty input (empty list/string/null/zero) — what is the specified result?
- [ ] Boundary values (first/last element, max size, off-by-one neighbors)
- [ ] Invalid input — does the test pin the *error contract* (type, message, status), not just "it raises"?
- [ ] Failure of each boundary dependency (timeout, 500, malformed response)
- [ ] Concurrency/idempotency where the contract promises it (double-submit, retry)

```python
# ❌ Only the demonstrated example
def test_divide():
    assert divide(10, 2) == 5

# ✅ Pins the error contract too
def test_divide_by_zero_raises():
    with pytest.raises(ZeroDivisionError):
        divide(10, 0)
```

🟡 Missing edge cases on new logic is important; 🔴 blocking when the untested path is security- or money-relevant.

---

## 6. Snapshot Abuse

Snapshots are legitimate for stable serialized output; they decay into "approve whatever changed" when used broadly.

**Check:**
- [ ] Snapshots cover small, stable artifacts — not whole pages/objects that change weekly
- [ ] The PR updates snapshots **with an explanation** of why the output changed; unexplained snapshot churn is a red flag
- [ ] Key behavior has explicit assertions alongside (or instead of) the snapshot

🟡 Unexplained snapshot updates are important — they can hide exactly the regression tests exist to catch.

---

## 7. Coverage vs Confidence

Coverage measures execution, not verification. A suite can hit 95% of lines and catch 0% of bugs (see §1–§2).

**The mutation question — apply it to every new test:**
> If I inverted the core condition, deleted a line, or swapped a constant in the code under test, would this test fail?

- If yes: the test has teeth.
- If no: it is documentation, not verification — flag it.

Where the project has a mutation-testing tool (Stryker, mutmut, pitest), a quick run on the changed module is the strongest evidence.

🔴 New critical logic with no test that would fail on inversion is blocking-equivalent to missing coverage.

---

## 8. Readability and Structure

Tests are documentation that runs. Review them for the same clarity as production code:

- [ ] Name states the behavior and condition: `rejects_expired_token`, not `test_auth_2`
- [ ] Arrange–Act–Assert visibly separated; one behavior per test
- [ ] Fixtures/builders hide irrelevant setup, expose the values the assertion depends on
- [ ] No logic in tests (loops/ifs computing expectations) — hardcode independently derived answers
- [ ] Test data is minimal and intentional; magic values carry a comment when non-obvious

🟢 Naming/structure issues are nits unless they hide what is actually asserted (then 🟡).

---

## Review Checklist

### Teeth
- [ ] 🔴 Every new test asserts concrete, independently derived behavior
- [ ] 🔴 The mutation question answered for each critical path: would it fail if the logic broke?
- [ ] 🔴 No test mocks the unit under test

### Reliability
- [ ] 🟡 No wall-clock sleeps, unseeded randomness, order dependence, or shared mutable state
- [ ] 🟡 Boundaries mocked realistically; internal logic kept real
- [ ] 🟡 Assertions on public contract, not internals

### Completeness
- [ ] 🟡 Empty/boundary/invalid inputs covered per the spec
- [ ] 🟡 Error contracts pinned (type/message/status), failure paths of dependencies tested
- [ ] 🔴 Security- or money-relevant paths have negative tests

### Hygiene
- [ ] 🟡 Snapshot updates explained in the PR
- [ ] 🟢 Names state behavior; AAA structure; no expectation-computing logic in tests

---

## Verdict Guidance

| Situation | Decision |
|-----------|----------|
| New critical logic, no test with teeth | 🔄 Request Changes |
| Tests exist but mirror the implementation | 🔄 Request Changes |
| Happy path covered, edges missing | 💬 Comment (🟡 items) |
| Flaky pattern with cheap fix | 💬 Comment (🟡 item) |
| Naming/structure only | ✅ Approve with 🟢 nits |
