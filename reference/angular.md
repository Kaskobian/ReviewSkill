# Angular Code Review Guide

> Angular 17+ code review guide covering Signals, standalone components, RxJS anti-patterns, zoneless change detection, template best practices and performance optimization.

## Table of Contents

- [Signals and Change Detection](#signals-and-change-detection)
- [Standalone Component Migration](#standalone-component-migration)
- [RxJS Anti-patterns](#rxjs-anti-patterns)
- [Zoneless Change Detection](#zoneless-change-detection)
- [Template Best Practices](#template-best-practices)
- [Performance Optimization](#performance-optimization)
- [Testing](#testing)
- [Route Guards](#route-guards)
- [Dependency Injection Patterns](#dependency-injection-patterns)
- [HttpInterceptor](#httpinterceptor)
- [Review Checklist](#review-checklist)

---

## Signals and Change Detection

### Signal + OnPush triggers change detection automatically

```typescript
// ❌ Mutable state + OnPush = UI does not update
@Component({
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<p>{{ data.name }}</p>`,
})
export class UserProfile {
  data = { name: 'Alice' };
  changeName() { this.data.name = 'Bob'; } // UI won't update when called outside a template event!
}

// ✅ Signal + OnPush = automatic change detection
@Component({
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<p>{{ name() }}</p>`,
})
export class UserProfile {
  name = signal('Alice');
  changeName() { this.name.set('Bob'); } // triggers CD automatically
}
```

### OnPush does not detect @Input() object mutation

```typescript
// ❌ Mutating the Input object - reference unchanged, OnPush does not detect it
@Input() config!: Config;
updateConfig() { this.config.theme = 'dark'; }

// ✅ Create a new reference
updateConfig() { this.config = { ...this.config, theme: 'dark' }; }
```

### computed() for derived state

```typescript
// ❌ effect to sync state - anti-pattern, may trigger extra CD cycles
export class CartComponent {
  total = signal(0);
  discounted = signal(0);

  constructor() {
    effect(() => this.discounted.set(this.total() * 0.9));
  }
}

// ✅ computed for derived state - lazy, no side effects
export class CartComponent {
  total = signal(0);
  discounted = computed(() => this.total() * 0.9);
}
```

### Signal reads after await in effect() are not tracked

```typescript
// ❌ Signal read after await - dependency not tracked
effect(async () => {
  const data = await fetchUserData();
  console.log(`Theme: ${theme()}`); // theme() is not tracked!
});

// ✅ Read synchronously before await
effect(async () => {
  const currentTheme = theme(); // synchronous read, tracked
  const data = await fetchUserData();
  console.log(`Theme: ${currentTheme}`);
});
```

### Use effect only in specific cases

```typescript
// ❌ Using effect to sync two Signals - always use computed
effect(() => { this.filtered.set(this.items().filter(i => i.active)); });

// ✅ Valid uses of effect: DOM manipulation, analytics logging, subscribing to external sources
effect(() => {
  const canvas = this.canvasRef.nativeElement;
  const ctx = canvas.getContext('2d')!;
  ctx.fillStyle = this.color();
  ctx.fillRect(0, 0, this.size(), this.size());
});

// 💡 "There are no situations where effect is good,
//    only situations where it is appropriate."
```

---

## Standalone Component Migration

### Standalone is the default in Angular 19+

```typescript
// ❌ Legacy NgModule component
@Component({
  selector: 'old-component',
  standalone: false,
})
export class OldComponent {}

// ✅ Modern standalone component (standalone is the default in Angular 19+)
@Component({
  selector: 'user-profile',
  imports: [ProfilePhoto, RouterLink],
  template: `<profile-photo /><a routerLink="/edit">Edit</a>`,
})
export class UserProfile {}
```

### Review flags

```typescript
// ⚠️ Signs that migration is needed:
// 1. standalone: false
// 2. @NgModule declarations
// 3. Components imported via NgModule instead of directly

// ✅ Migration path:
// 1. Remove standalone: false
// 2. Add dependencies to the component's imports array
// 3. Delete the NgModule once it has no declarations left
```

---

## RxJS Anti-patterns

### subscribe() must be paired with takeUntilDestroyed

```typescript
// ❌ Bare subscribe - memory leak! Keeps receiving data after the component is destroyed
@Component({ /* ... */ })
export class UserProfile implements OnInit {
  ngOnInit() {
    this.data$.subscribe(data => this.processData(data));
  }
}

// ✅ takeUntilDestroyed - unsubscribes automatically on destroy (call it in the constructor or an injection context)
@Component({ /* ... */ })
export class UserProfile {
  constructor() {
    this.data$.pipe(takeUntilDestroyed()).subscribe(data => {
      this.processData(data);
    });
  }
}

// ✅ Outside the constructor - pass a DestroyRef
@Component({ /* ... */ })
export class UserProfile {
  private destroyRef = inject(DestroyRef);

  startListening() {
    this.data$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(/* ... */);
  }
}
```

### toSignal over AsyncPipe

```typescript
// ❌ AsyncPipe - needs an import, | async in the template
@Component({
  imports: [AsyncPipe],
  template: `{{ data$ | async }}`,
})

// ✅ toSignal - unsubscribes automatically; must be called in an injection context
export class UserProfile {
  data = toSignal(this.data$, { initialValue: null });
  // use data() directly in the template
}
```

### Avoid repeated toSignal calls

```typescript
// ❌ Every toSignal call creates a new subscription
getData() {
  return toSignal(this.http.get('/api/data'));
}

// ✅ Store the result
data = toSignal(this.http.get('/api/data'), { initialValue: null });
```

---

## Zoneless Change Detection

### Plain property mutations are not detected (zoneless, the default in Angular 21+)

```typescript
// ❌ In zoneless, plain property assignment does not trigger CD
export class UserService {
  user: User | null = null;
  loadUser() { this.user = fetchResult; } // does not trigger!
}

// ✅ Signals trigger CD automatically
export class UserService {
  private _user = signal<User | null>(null);
  readonly user = this._user.asReadonly();
  loadUser() { this._user.set(fetchResult); }
}
```

### NgZone APIs stop working in zoneless

```typescript
// ❌ NgZone.onStable never fires in zoneless
ngZone.onStable.subscribe(() => { /* never fires */ });

// ✅ Use afterNextRender
afterNextRender({ write: () => { /* runs after CD */ } });
```

### Reactive Forms mutations need markForCheck

```typescript
// ❌ Reactive Forms setValue/patchValue do not schedule CD automatically in zoneless
this.form.patchValue({ name: 'Alice' }); // UI may not update

// ✅ Mark manually or reflect via a Signal
this.form.patchValue({ name: 'Alice' });
this.cdr.markForCheck();
```

### Valid CD triggers in zoneless

| Trigger | Notes |
|--------|------|
| `signal.set()` / `.update()` | Signal updates trigger automatically |
| `ChangeDetectorRef.markForCheck()` | Manual marking |
| `ComponentRef.setInput()` | Input binding |
| Template event listener callbacks | User interaction |

---

## Template Best Practices

### Extract complex logic into computed Signals

```typescript
// ❌ Complex expression in the template
template: `<div *ngIf="items.filter(i => i.active).length > 0 && user.role === 'admin'">`

// ✅ Extract into computed
filteredItems = computed(() => this.items().filter(i => i.active));
shouldShow = computed(() => this.filteredItems().length > 0 && this.user().role === 'admin');
template: `@if (shouldShow()) { <div>...</div> }`
```

### Native bindings over NgClass / NgStyle

```typescript
// ❌ NgClass/NgStyle - extra directive overhead
template: `<div [ngClass]="{active: isActive}" [ngStyle]="{'color': textColor}">`

// ✅ Native class/style bindings - better performance
template: `<div [class.active]="isActive" [style.color]="textColor">`
```

### Mark template-only members protected

```typescript
// ❌ Template-only method exposed as public
export class UserProfile {
  formatName(name: string) { return name.trim(); }
}

// ✅ Use protected for template-only members
export class UserProfile {
  protected formatName(name: string) { return name.trim(); }
}
```

### Mark Angular-managed properties readonly

```typescript
// ❌ input/output/model can be overwritten by accident
userId = input<string>();
userSaved = output<void>();

// ✅ readonly prevents accidental assignment
readonly userId = input<string>();
readonly userSaved = output<void>();
readonly userName = model<string>();
```

### Naming: name handlers after the action, not the event

```typescript
// ❌ Named after the event
template: `<button (click)="handleClick()">Save</button>`

// ✅ Named after the action
template: `<button (click)="saveUserData()">Save</button>`
```

---

## Performance Optimization

### effect is a last resort - prefer computed

```typescript
// ❌ effect for state sync - extra CD, possible infinite loop
effect(() => {
  this.filteredItems.set(this.items().filter(i => i.active));
});

// ✅ computed - lazy, no side effects, no extra CD
filteredItems = computed(() => this.items().filter(i => i.active));
```

### afterRenderEffect separates read and write phases

```typescript
// ❌ No phase specified = mixedReadWrite = extra DOM reflow
afterRenderEffect(() => {
  const height = el.offsetHeight; // read
  el.style.height = height + 10 + 'px'; // write
});

// ✅ Separate phases to reduce reflow
afterRenderEffect({
  earlyRead: () => el.offsetHeight,
  write: (height) => { el.style.height = height() + 10 + 'px'; },
  read: () => verifyLayout(),
});
```

### inject() over constructor injection

```typescript
// ❌ Constructor injection - hard to read with many dependencies
export class UserService {
  constructor(
    private http: HttpClient,
    private router: Router,
    private auth: AuthService,
  ) {}
}

// ✅ inject() - better type inference and readability
export class UserService {
  private http = inject(HttpClient);
  private router = inject(Router);
  private auth = inject(AuthService);
}
```

---

## Testing

### Component tests (TestBed)

```typescript
// ✅ Standalone component test
@Component({
  standalone: true,
  template: `<button (click)="increment()">{{ count() }}</button>`,
})
export class CounterComponent {
  count = signal(0);
  increment() { this.count.update(c => c + 1); }
}

describe('CounterComponent', () => {
  let fixture: ComponentFixture<CounterComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [CounterComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(CounterComponent);
    fixture.detectChanges();
  });

  it('should increment on click', () => {
    const button = fixture.nativeElement.querySelector('button');
    button.click();
    fixture.detectChanges();
    expect(button.textContent.trim()).toBe('1');
  });
});
```

### Service tests (DI mocks)

```typescript
// ✅ Use TestBed.inject + provide overrides
@Injectable({ providedIn: 'root' })
export class UserService {
  private http = inject(HttpClient);
  getUser(id: number) {
    return this.http.get<User>(`/api/users/${id}`);
  }
}

describe('UserService', () => {
  let service: UserService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(UserService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('should fetch user', () => {
    const mockUser = { id: 1, name: 'Alice' };

    service.getUser(1).subscribe(user => {
      expect(user).toEqual(mockUser);
    });

    const req = httpMock.expectOne('/api/users/1');
    expect(req.request.method).toBe('GET');
    req.flush(mockUser);
  });
});
```

### Integration test strategy

```typescript
// ❌ Over-mocking - tests the mock, not real behavior
provideHttpClient: () => ({
  get: jasmine.createSpy().and.returnValue(of(mockData)),
}),

// ✅ Use HttpTestingController to verify real HTTP interaction
TestBed.configureTestingModule({
  providers: [
    provideHttpClient(),
    provideHttpClientTesting(),
  ],
});

// ✅ Verify the component passes inputs down to its children
describe('UserProfile', () => {
  it('should pass user to child', () => {
    const fixture = TestBed.createComponent(UserProfile);
    fixture.componentRef.setInput('user', testUser);
    fixture.detectChanges();

    const child = fixture.debugElement.query(By.directive(UserAvatar));
    expect(child.componentInstance.user()).toEqual(testUser);
  });
});
```

---

## Route Guards

### AuthGuard / CanActivate

```typescript
// ✅ Functional route guard (recommended since Angular 15)
export const authGuard: CanActivateFn = (route, state) => {
  const auth = inject(AuthService);
  const router = inject(Router);

  if (auth.isAuthenticated()) return true;

  return router.createUrlTree(['/login'], {
    queryParams: { returnUrl: state.url },
  });
};

// Usage
export const routes: Routes = [
  {
    path: 'dashboard',
    component: DashboardComponent,
    canActivate: [authGuard],
  },
];
```

### Guards on lazy-loaded routes

```typescript
// ✅ The guard is resolved only when the route loads
// auth.guard.ts
export const authGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  return auth.isAuthenticated();
};

// routes.ts
export const routes: Routes = [
  {
    path: 'admin',
    loadChildren: () => import('./admin/routes').then(m => m.routes),
    canActivate: [authGuard],
  },
];
```

### Parameterized route guards

```typescript
// ✅ Guard with a roles parameter
export function roleGuard(allowedRoles: string[]): CanActivateFn {
  return (route, state) => {
    const auth = inject(AuthService);
    const user = auth.currentUser();
    return user ? allowedRoles.includes(user.role) : false;
  };
}

// Usage
{
  path: 'admin',
  component: AdminComponent,
  canActivate: [roleGuard(['admin', 'superadmin'])],
}
```

### CanDeactivate guard

```typescript
// ✅ Prevent navigating away with unsaved changes
export const unsavedChangesGuard: CanDeactivateFn<EditFormComponent> = (
  component
) => {
  if (component.hasUnsavedChanges()) {
    return confirm('You have unsaved changes. Leave anyway?');
  }
  return true;
};
```

---

## Dependency Injection Patterns

### Using InjectionToken

```typescript
// ❌ String tokens - collision-prone, no type safety
providers: [{ provide: 'API_URL', useValue: 'https://api.example.com' }]

// ✅ InjectionToken provides type safety
export const API_URL = new InjectionToken<string>('API_URL');

providers: [{ provide: API_URL, useValue: 'https://api.example.com' }]

// Usage
private apiUrl = inject(API_URL);
```

### Hierarchical providers

```typescript
// ✅ Different injection levels
// Root level - global singleton
@Injectable({ providedIn: 'root' })
export class GlobalService {}

// Component level - one instance per component
@Component({
  providers: [LocalService],
})
export class MyComponent {
  private local = inject(LocalService);
}

// Route level - shared by the route and its children
{
  path: 'checkout',
  providers: [CheckoutService],
  children: [/* ... */],
}
```

### Factory providers

```typescript
// ✅ Provide different implementations depending on conditions
export const themeProvider: FactoryProvider = {
  provide: ThemeService,
  useFactory: () => {
    const platform = inject(PLATFORM_ID);
    if (isPlatformServer(platform)) {
      return new ServerThemeService();
    }
    return new BrowserThemeService();
  },
};

// ✅ Configure from the environment
export const apiConfigProvider: FactoryProvider = {
  provide: ApiConfig,
  useFactory: () => {
    const env = inject(ENVIRONMENT);
    return env.production
      ? new ProductionApiConfig()
      : new DevelopmentApiConfig();
  },
};
```

---

## HttpInterceptor

### Auth token interceptor

```typescript
// ✅ Functional interceptor - attaches the auth token automatically
export function authInterceptor(
  req: HttpRequest<unknown>,
  next: HttpHandlerFn
): Observable<HttpEvent<unknown>> {
  const token = inject(AuthService).token();
  if (!token) return next(req);

  return next(req.clone({
    setHeaders: { Authorization: `Bearer ${token}` },
  }));
}

// Registration
provideHttpClient(withInterceptors([authInterceptor]))
```

### Error handling interceptor

```typescript
// ✅ Functional interceptor - centralized error handling
export function errorInterceptor(
  req: HttpRequest<unknown>,
  next: HttpHandlerFn
): Observable<HttpEvent<unknown>> {
  const router = inject(Router);

  return next(req).pipe(
    catchError((error: HttpErrorResponse) => {
      if (error.status === 401) {
        router.navigate(['/login']);
      }
      if (error.status === 500) {
        console.error('Server error:', error);
      }
      return throwError(() => error);
    })
  );
}
```

### Request/response transformation

```typescript
// ✅ Functional interceptor - automatic camelCase ↔ snake_case
export function transformInterceptor(
  req: HttpRequest<unknown>,
  next: HttpHandlerFn
): Observable<HttpEvent<unknown>> {
  const transformedBody = req.body ? toSnakeCase(req.body) : null;
  const transformedReq = req.clone({ body: transformedBody });

  return next(transformedReq).pipe(
    map(event => {
      if (event instanceof HttpResponse) {
        return event.clone({ body: toCamelCase(event.body) });
      }
      return event;
    })
  );
}
```

### Interceptor order

```typescript
// ✅ Interceptors run in registration order
// Request: A → B → C → backend
// Response: backend → C → B → A
provideHttpClient(
  withInterceptors([
    authInterceptor,
    loggingInterceptor,
    errorInterceptor,
  ])
)
```

## Review Checklist

### Signals and Change Detection

- [ ] Signal + OnPush for template state (not mutable objects)
- [ ] `@Input()` objects updated via new references (not mutation)
- [ ] Derived state uses `computed()`, not `effect()`
- [ ] Signal reads in `effect()` happen before `await`
- [ ] `effect()` used only for DOM manipulation, logging, external source subscriptions

### Standalone Components

- [ ] No `standalone: false` (Angular 19+)
- [ ] Components import dependencies via the `imports` array
- [ ] No unnecessary `@NgModule`

### RxJS

- [ ] `.subscribe()` paired with `takeUntilDestroyed` or the `async` pipe
- [ ] Prefer `toSignal` over `AsyncPipe`
- [ ] No repeated `toSignal` calls

### Zoneless

- [ ] Template state managed via Signals (not plain properties)
- [ ] No `NgZone.onStable` / `NgZone.onMicrotaskEmpty`
- [ ] `markForCheck()` after Reactive Forms mutations

### Templates

- [ ] Complex logic extracted into `computed` Signals
- [ ] Native `[class]`/`[style]` used instead of `NgClass`/`NgStyle`
- [ ] Template-only members marked `protected`
- [ ] `input`/`output`/`model` properties marked `readonly`
- [ ] Event handlers named after the action (`saveData`, not `handleClick`)

### Performance

- [ ] `effect()` not used for state sync
- [ ] `afterRenderEffect` separates read and write phases
- [ ] `inject()` used for dependency injection
