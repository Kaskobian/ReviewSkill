# Security Review Guide

Security-focused code review checklist based on OWASP Top 10 and best practices.

For a full audit (whole repo, release gate, "OWASP review") use the [OWASP Security Audit](owasp-security-audit.md) procedure and `scripts/security-scan.py`. To fix what it finds, use the [Remediation Playbook](remediation-playbook.md).

## Authentication & Authorization

### Authentication
- [ ] Passwords hashed with strong algorithm (bcrypt, argon2)
- [ ] Password policy follows NIST 800-63B: minimum length, long maximum (>= 64), all characters allowed, checked against breached/common password lists; no forced composition rules or periodic rotation
- [ ] Account lockout after failed attempts
- [ ] Secure password reset flow
- [ ] Multi-factor authentication for sensitive operations
- [ ] Session tokens are cryptographically random
- [ ] Session timeout implemented

### Authorization
- [ ] Authorization checks on every request
- [ ] Principle of least privilege applied
- [ ] Role-based access control (RBAC) properly implemented
- [ ] No privilege escalation paths
- [ ] Direct object reference checks (IDOR prevention)
- [ ] API endpoints protected appropriately

### JWT Security
```typescript
// ❌ Insecure JWT configuration
jwt.sign(payload, 'weak-secret');

// ✅ Secure JWT configuration (asymmetric: sign with the private key, verify with the public key)
// For a single service, a >= 256-bit random secret with HS256 (and algorithms: ['HS256'] on verify) is also fine.
jwt.sign(payload, process.env.JWT_PRIVATE_KEY, {  // PEM-encoded RSA private key
  algorithm: 'RS256',
  expiresIn: '15m',
  issuer: 'your-app',
  audience: 'your-api'
});

// ❌ Not verifying JWT properly
const decoded = jwt.decode(token);  // No signature verification!

// ✅ Verify signature and claims
const decoded = jwt.verify(token, publicKey, {
  algorithms: ['RS256'],
  issuer: 'your-app',
  audience: 'your-api'
});
```

## Input Validation

### SQL Injection Prevention

**The #1 rule**: Always use parameterized queries. Never concatenate user input into SQL strings.

Every major language and framework has a parameterized query mechanism:
- Python: `cursor.execute("SELECT ...", params)` / ORM filter methods
- Java: `PreparedStatement` / JPA `@Query` with `@Param`
- Go: `db.Query("SELECT ...", args...)`
- Node.js: `client.query("SELECT ...", [args])` / Prisma ORM
- PHP: PDO prepared statements / Laravel Eloquent
- C#: ADO.NET `SqlParameter` / Dapper / EF Core LINQ

> **See [SQL Injection Prevention Guide](cross-cutting/sql-injection-prevention.md) for complete cross-language examples, ORM unsafe patterns, dynamic identifier handling, and detection tools.**

### XSS Prevention

**The #1 rule**: Rely on framework auto-escaping. Audit every escape hatch.

Every major framework auto-escapes by default:
- React: JSX auto-escapes. Audit `dangerouslySetInnerHTML`.
- Vue: `{{ }}` auto-escapes. Audit `v-html`.
- Angular: Interpolation auto-escapes. Audit `bypassSecurityTrustHtml`.
- Svelte: `{ }` auto-escapes. Audit `{@html}`.
- Django: Templates auto-escape. Audit `mark_safe`.

For defense-in-depth, configure Content Security Policy (CSP) with nonce-based `script-src`.

> **See [XSS Prevention Guide](cross-cutting/xss-prevention.md) for complete cross-framework examples, CSP configuration, input validation vs output encoding, and detection tools.**

### CSRF Prevention

**CSRF Token Implementation**
```typescript
// ✅ Server: generate and validate CSRF token
import crypto from 'node:crypto';

function generateCsrfToken(): string {
  return crypto.randomBytes(32).toString('hex');
}

// Middleware: validate token on state-changing requests
app.post('/api/data', (req, res) => {
  const token = req.headers['x-csrf-token'];
  const sessionToken = req.session.csrfToken;
  if (!token || token !== sessionToken) {
    return res.status(403).json({ error: 'Invalid CSRF token' });
  }
  // ...handle request
});
```

**Python (Django)**
```python
# ✅ Django: built-in CSRF protection
# settings.py
MIDDLEWARE = [
    'django.middleware.csrf.CsrfViewMiddleware',  # enabled by default
]

# templates: include CSRF token
# <form method="post">
#   {% csrf_token %}
# </form>

# ❌ Disabling CSRF on a view
@csrf_exempt  # avoid unless absolutely necessary
def my_view(request):
    ...
```

**Java (Spring Boot)**
```java
// ✅ Spring Security: CSRF enabled by default
@Configuration
@EnableWebSecurity
public class SecurityConfig {
    @Bean
    public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.csrf(csrf -> csrf
            .csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse())
        );
        return http.build();
    }
}
```

**SameSite Cookie**
```typescript
// ✅ Set SameSite cookie as additional defense
res.cookie('session', sessionId, {
  httpOnly: true,
  secure: true,
  sameSite: 'strict',  // or 'lax' to allow top-level navigation GET requests
  maxAge: 3600000,
});
```

### SSRF Prevention

```python
# ❌ Vulnerable: user-controlled URL
import requests
url = request.GET.get('url')
response = requests.get(url)

# ✅ Validate URL against whitelist
ALLOWED_HOSTS = ['api.example.com', 'cdn.example.com']

def is_safe_url(url: str) -> bool:
    from urllib.parse import urlparse
    parsed = urlparse(url)
    return parsed.scheme == "https" and parsed.hostname in ALLOWED_HOSTS

if is_safe_url(url):
    # no redirects: an open redirect on an allowed host would reach internal targets
    response = requests.get(url, allow_redirects=False, timeout=5)
```

```typescript
// ❌ Vulnerable: fetching arbitrary URLs
const url = req.query.url;
const response = await fetch(url);

// ✅ Validate URL before fetching
const ALLOWED_DOMAINS = ['api.internal.com'];

function isSafeUrl(url: string): boolean {
  try {
    const parsed = new URL(url);
    // Allowlist, not a denylist of "internal" addresses: denylists miss IPv6, 169.254.*, decimal IPs, DNS tricks
    return parsed.protocol === 'https:' && ALLOWED_DOMAINS.includes(parsed.hostname);
  } catch {
    return false;
  }
}

if (isSafeUrl(url)) {
  const response = await fetch(url, { redirect: 'error' });  // do not follow redirects off the allowlist
}
```

```go
// ❌ Go: a string denylist ("localhost", "127.0.0.1") is not a defence — it misses 127.0.0.2, [::1],
// 10.x, 169.254.169.254, DNS names resolving to internal addresses, and redirects.

// ✅ Go: prefer an explicit host allowlist. If arbitrary hosts must be allowed,
// check the *resolved* IP at connect time (covers DNS tricks, rebinding, redirects).
func ssrfSafeClient() *http.Client {
    dialer := &net.Dialer{
        Timeout: 5 * time.Second,
        Control: func(network, address string, _ syscall.RawConn) error {
            host, _, err := net.SplitHostPort(address)
            if err != nil {
                return err
            }
            ip := net.ParseIP(host)
            if ip == nil || ip.IsLoopback() || ip.IsPrivate() || ip.IsUnspecified() ||
                ip.IsLinkLocalUnicast() || ip.IsLinkLocalMulticast() || ip.IsMulticast() {
                return fmt.Errorf("blocked destination %s", address)
            }
            return nil
        },
    }
    return &http.Client{
        Timeout:   10 * time.Second,
        Transport: &http.Transport{DialContext: dialer.DialContext}, // no Proxy: checks apply to the real target
        CheckRedirect: func(req *http.Request, via []*http.Request) error {
            if req.URL.Scheme != "https" || len(via) >= 3 {
                return http.ErrUseLastResponse
            }
            return nil
        },
    }
}
```

### IDOR (Insecure Direct Object Reference)

```python
# ❌ Vulnerable: no ownership check
def get_order(request, order_id):
    order = Order.objects.get(id=order_id)  # any user can view any order
    return JsonResponse(order.to_dict())

# ✅ Check ownership before returning
def get_order(request, order_id):
    order = Order.objects.filter(id=order_id, user=request.user).first()
    if not order:
        return JsonResponse({'error': 'Not found'}, status=404)
    return JsonResponse(order.to_dict())
```

```typescript
// ❌ Vulnerable: no authorization check
app.get('/api/orders/:id', async (req, res) => {
  const order = await db.order.findUnique({
    where: { id: Number(req.params.id) }
  });
  res.json(order);
});

// ✅ Include user context in query
app.get('/api/orders/:id', async (req, res) => {
  const order = await db.order.findFirst({
    where: {
      id: Number(req.params.id),
      userId: req.user.id,  // Scope to current user
    }
  });
  if (!order) return res.status(404).json({ error: 'Not found' });
  res.json(order);
});
```

```java
// ✅ Spring Security: method-level authorization
@GetMapping("/api/orders/{id}")
@PreAuthorize("@orderService.isOwner(#id, authentication.principal.id)")
public Order getOrder(@PathVariable Long id) {
    return orderService.findById(id);
}
```

**UUID vs Auto-Increment ID**
```typescript
// ❌ Auto-increment IDs can be enumerated
// GET /api/users/1, /api/users/2, /api/users/3 ...

// ✅ Random UUIDs (v4) are unpredictable (time-based v1 are not)
// GET /api/users/550e8400-e29b-41d4-a716-446655440000

// ⚠️ UUIDs only prevent enumeration; they are not access control
// You still must verify the current user may access the resource
```

### Command Injection Prevention

**Python**
```python
# ❌ Vulnerable: shell=True
import subprocess
subprocess.run(f"convert {filename} output.png", shell=True)

# ✅ Use list arguments without shell
subprocess.run(['convert', filename, 'output.png'], check=True)

# ✅ Validate and sanitize input
import shlex
safe_filename = shlex.quote(filename)
```

**Node.js**
```typescript
// ❌ Vulnerable: exec with string interpolation
import { exec } from 'node:child_process';
exec(`convert ${filename} output.png`);

// ✅ Use execFile with array arguments
import { execFile } from 'node:child_process';
execFile('convert', [filename, 'output.png'], (error, stdout) => {
  if (error) throw error;
});

// ❌ Never pass user input to shell
exec(`echo ${userInput}`);  // userInput = "; rm -rf /"

// ✅ Sanitize or use non-shell alternatives
import { writeFile } from 'node:fs/promises';
await writeFile('output.txt', userInput);  // No shell involved
```

**Go**
```go
// ❌ Vulnerable: shell command with user input
cmd := exec.Command("sh", "-c", "echo " + userInput)

// ✅ Use exec.Command with separate arguments
cmd := exec.Command("echo", userInput)

// ❌ Passing user input to shell
out, _ := exec.Command("bash", "-c", "cat "+filename).Output()

// ✅ Read file directly without shell
data, err := os.ReadFile(filename)
```

**Java**
```java
// ❌ Vulnerable: Runtime.exec with string concatenation
Runtime.getRuntime().exec("convert " + filename + " output.png");

// ✅ Use ProcessBuilder with separate arguments
ProcessBuilder pb = new ProcessBuilder("convert", filename, "output.png");
Process process = pb.start();

// ❌ Dangerous: passing user input to shell
Runtime.getRuntime().exec(new String[]{"sh", "-c", "echo " + userInput});
```

## Data Protection

### Sensitive Data Handling
- [ ] No secrets in source code
- [ ] Secrets stored in environment variables or secret manager
- [ ] Sensitive data encrypted at rest
- [ ] Sensitive data encrypted in transit (HTTPS)
- [ ] PII handled according to regulations (GDPR, etc.)
- [ ] Sensitive data not logged
- [ ] Secure data deletion when required

### Configuration Security
```yaml
# ❌ Secrets in config files
database:
  password: "super-secret-password"

# ✅ Reference environment variables
database:
  password: ${DATABASE_PASSWORD}
```

### Error Messages
```typescript
// ❌ Leaking sensitive information
catch (error) {
  return res.status(500).json({
    error: error.stack,  // Exposes internal details
    query: sqlQuery      // Exposes database structure
  });
}

// ✅ Generic error messages
catch (error) {
  logger.error('Database error', { error, userId });  // Log internally
  return res.status(500).json({
    error: 'An unexpected error occurred'
  });
}
```

## API Security

### Rate Limiting
- [ ] Rate limiting on all public endpoints
- [ ] Stricter limits on authentication endpoints
- [ ] Per-user and per-IP limits
- [ ] Graceful handling when limits exceeded

### CORS Configuration
```typescript
// ❌ Overly permissive CORS
app.use(cors({ origin: '*' }));

// ✅ Restrictive CORS
app.use(cors({
  origin: ['https://your-app.com'],
  methods: ['GET', 'POST'],
  credentials: true
}));
```

### HTTP Headers
```typescript
// Security headers to set
app.use(helmet({
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      scriptSrc: ["'self'"],
      styleSrc: ["'self'", "'unsafe-inline'"],
    }
  },
  hsts: { maxAge: 31536000, includeSubDomains: true },
  noSniff: true,
  xssFilter: true,
  frameguard: { action: 'deny' }
}));
```

## Cryptography

### Secure Practices
- [ ] Using well-established algorithms (AES-256, RSA-2048+)
- [ ] Not implementing custom cryptography
- [ ] Using cryptographically secure random number generation
- [ ] Proper key management and rotation
- [ ] Secure key storage (HSM, KMS)

### Common Mistakes
```typescript
// ❌ Weak random generation
const token = Math.random().toString(36);

// ✅ Cryptographically secure random
const crypto = require('crypto');
const token = crypto.randomBytes(32).toString('hex');

// ❌ MD5/SHA1 for passwords
const hash = crypto.createHash('md5').update(password).digest('hex');

// ✅ Use bcrypt or argon2
const bcrypt = require('bcrypt');
const hash = await bcrypt.hash(password, 12);
```

## Dependency Security

### Checklist
- [ ] Dependencies from trusted sources only
- [ ] No known vulnerabilities (npm audit, cargo audit)
- [ ] Dependencies kept up to date
- [ ] Lock files committed (package-lock.json, Cargo.lock)
- [ ] Minimal dependency usage
- [ ] License compliance verified

### Audit Commands
```bash
# Node.js
npm audit
npm audit fix

# Python
pip-audit
safety scan

# Rust
cargo audit

# General
snyk test
```

## Logging & Monitoring

### Secure Logging
- [ ] No sensitive data in logs (passwords, tokens, PII)
- [ ] Logs protected from tampering
- [ ] Appropriate log retention
- [ ] Security events logged (login attempts, permission changes)
- [ ] Log injection prevented

```typescript
// ❌ Logging sensitive data
logger.info(`User login: ${email}, password: ${password}`);

// ✅ Safe logging
logger.info('User login attempt', { email, success: true });
```

## Security Review Severity Levels

| Severity | Description | Action |
|----------|-------------|--------|
| **Critical** | Immediate exploitation possible, data breach risk | Block merge, fix immediately |
| **High** | Significant vulnerability, requires specific conditions | Block merge, fix before release |
| **Medium** | Moderate risk, defense in depth concern | Should fix, can merge with tracking |
| **Low** | Minor issue, best practice violation | Nice to fix, non-blocking |
| **Info** | Suggestion for improvement | Optional enhancement |
