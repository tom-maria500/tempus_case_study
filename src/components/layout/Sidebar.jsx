import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { LayoutDashboard } from 'lucide-react';

const navItems = [
  { id: 'providers', label: 'Provider Intelligence', icon: LayoutDashboard, route: '/' }
];

export function Sidebar({ active = 'providers' }) {
  const location = useLocation();

  const isActive = (item) => location.pathname === item.route;

  return (
    <aside className="flex h-full w-60 flex-col border-r border-bg-border bg-bg-secondary shadow-tempus">
      <div className="flex items-center gap-2 px-5 py-5 border-b border-bg-border">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-bg-tertiary text-accent-primary text-lg font-semibold">
          T
        </div>
        <div className="flex flex-col">
          <span className="text-sm font-semibold tracking-[0.16em] text-text-primary">
            TEMPUS
          </span>
          <span className="text-xs font-medium text-accent-primary">
            Sales Copilot
          </span>
        </div>
      </div>

      <nav className="flex-1 space-y-1 px-3 py-4 text-sm">
        {navItems.map((item) => {
          const Icon = item.icon;
          const itemActive = isActive(item);
          return (
            <Link
              key={item.id}
              to={item.route}
              className={[
                'group flex w-full items-center justify-between rounded-md px-3 py-2 text-left transition-colors duration-150',
                itemActive
                  ? 'border-l-2 border-accent-primary bg-bg-secondary font-semibold text-text-primary'
                  : 'text-text-secondary hover:bg-bg-tertiary hover:text-text-primary'
              ].join(' ')}
            >
              <div className="flex items-center gap-3">
                <Icon className="h-4 w-4" />
                <span>{item.label}</span>
              </div>
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-bg-border px-4 py-4 text-[11px] text-text-secondary">
        <div className="inline-flex items-center gap-2 rounded-badge bg-bg-tertiary px-3 py-1">
          <span className="h-1.5 w-1.5 rounded-full bg-accent-primary" />
          <span>Powered by Tempus AI</span>
        </div>
      </div>
    </aside>
  );
}

