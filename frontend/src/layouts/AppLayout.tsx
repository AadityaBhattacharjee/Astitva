import { useEffect, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  Compass,
  Home,
  LifeBuoy,
  Map,
  MessageCircleHeart,
  Settings,
  Shield,
  TrendingUp,
  User as UserIcon,
  LogOut,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { useAuth } from "@/hooks/use-auth";
import { LoadingState } from "@/components/astitva/States";

const navItems = [
  { to: "/dashboard", label: "Home", icon: Home },
  { to: "/roadmap", label: "Roadmap", icon: Map },
  { to: "/chat", label: "Guide", icon: MessageCircleHeart },
  { to: "/progress", label: "Progress", icon: TrendingUp },
  { to: "/profile", label: "Profile", icon: UserIcon },
  { to: "/opportunities", label: "Explore", icon: Compass },
] as const;

const mobileItems = navItems.slice(0, 5);

export function AppLayout({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  const { hydrated, isAuthenticated, user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    if (hydrated && !isAuthenticated) {
      void navigate("/login", { replace: true });
    }
  }, [hydrated, isAuthenticated, navigate]);

  if (!hydrated || !isAuthenticated) {
    return (
      <div className="mx-auto max-w-md px-6 py-24">
        <LoadingState message="Opening your secure session…" />
      </div>
    );
  }

  const initials = user?.email?.slice(0, 2).toUpperCase() ?? "A";

  return (
    <div className="min-h-dvh bg-background">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-3 focus:left-3 focus:z-50 focus:rounded-full focus:bg-primary focus:px-4 focus:py-2 focus:text-primary-foreground"
      >
        Skip to content
      </a>

      <div className="flex">
        {/* Sidebar (desktop) */}
        <aside className="sticky top-0 hidden h-dvh w-64 shrink-0 flex-col border-r border-border bg-surface px-4 py-6 lg:flex">
          <Link to="/dashboard" className="flex items-center gap-2 px-2">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary text-sm font-bold text-primary-foreground">
              A
            </span>
            <span className="font-display text-lg font-bold tracking-tight">ASTITVA</span>
          </Link>

          <nav className="mt-8 flex flex-col gap-1" aria-label="Main">
            {navItems.map((item) => {
              const active = location.pathname.startsWith(item.to);
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  className={cn(
                    "flex min-h-11 items-center gap-3 rounded-xl px-3 text-sm font-medium transition-colors",
                    active
                      ? "bg-primary text-primary-foreground"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground",
                  )}
                >
                  <item.icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                  {item.label}
                </Link>
              );
            })}
          </nav>

          <div className="mt-auto space-y-2">
            <Link
              to="/settings"
              className={cn(
                "flex min-h-11 items-center gap-3 rounded-xl px-3 text-sm font-medium transition-colors",
                location.pathname.startsWith("/settings")
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground",
              )}
            >
              <Settings className="h-4 w-4" aria-hidden="true" />
              Settings
            </Link>
            <button
              onClick={logout}
              className="flex min-h-11 w-full items-center gap-3 rounded-xl px-3 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <LogOut className="h-4 w-4" aria-hidden="true" />
              Sign out
            </button>
            <p className="flex items-center gap-2 rounded-xl bg-accent-soft px-3 py-2 text-xs text-muted-foreground">
              <Shield className="h-3.5 w-3.5 shrink-0 text-accent" aria-hidden="true" />
              JWT-secured session
            </p>
          </div>
        </aside>

        {/* Main area */}
        <div className="min-w-0 flex-1">
          <header className="sticky top-0 z-30 border-b border-border bg-background/90 backdrop-blur">
            <div className="mx-auto grid max-w-5xl grid-cols-[minmax(0,1fr)_auto] items-center gap-4 px-5 py-4">
              <div className="min-w-0">
                <Link to="/dashboard" className="lg:hidden">
                  <span className="font-display text-sm font-bold tracking-tight">ASTITVA</span>
                </Link>
                <h1 className="truncate text-xl font-bold text-foreground sm:text-2xl">{title}</h1>
                {subtitle ? (
                  <p className="truncate text-sm text-muted-foreground">{subtitle}</p>
                ) : null}
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <Link
                  to="/chat"
                  aria-label="Open Astitva Guide"
                  className="hidden min-h-11 min-w-11 items-center justify-center rounded-full border border-border text-foreground hover:border-primary hover:text-primary sm:inline-flex"
                >
                  <LifeBuoy className="h-4 w-4" aria-hidden="true" />
                </Link>
                <Link
                  to="/profile"
                  aria-label="Your profile"
                  className="flex h-11 w-11 items-center justify-center rounded-full bg-secondary-soft text-sm font-semibold text-foreground"
                >
                  {initials}
                </Link>
              </div>
            </div>
          </header>

          <main id="main-content" className="mx-auto max-w-5xl px-5 pt-6 pb-28 lg:pb-12">
            {children}
          </main>
        </div>
      </div>

      {/* Mobile bottom nav */}
      <nav
        aria-label="Primary mobile"
        className="fixed inset-x-0 bottom-0 z-40 border-t border-border bg-surface lg:hidden"
      >
        <ul className="mx-auto flex max-w-lg">
          {mobileItems.map((item) => {
            const active = location.pathname.startsWith(item.to);
            return (
              <li key={item.to} className="flex-1">
                <Link
                  to={item.to}
                  className={cn(
                    "flex min-h-14 flex-col items-center justify-center gap-1 px-1 text-[11px] font-medium",
                    active ? "text-primary" : "text-muted-foreground",
                  )}
                >
                  <item.icon className="h-5 w-5" aria-hidden="true" />
                  {item.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </div>
  );
}
