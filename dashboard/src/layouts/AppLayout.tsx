import {
  AppShell,
  Sidebar,
  SidebarCollapseButton,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarHeader,
  SidebarItem,
} from "@adlimen/ui-react";
import { Outlet, useNavigate, useRouterState } from "@tanstack/react-router";
import type { ReactNode } from "react";

interface NavItem {
  label: string;
  path: string;
  icon: ReactNode;
}

const NAV_ITEMS: NavItem[] = [
  { label: "Workflows", path: "/workflows", icon: <span aria-hidden="true">⚙️</span> },
  { label: "Agents", path: "/agents", icon: <span aria-hidden="true">🤖</span> },
  { label: "Audit Log", path: "/audit", icon: <span aria-hidden="true">📋</span> },
];

export function AppLayout() {
  const navigate = useNavigate();
  const location = useRouterState({ select: (s) => s.location });

  const isActive = (path: string) => location.pathname.startsWith(path);

  return (
    <AppShell>
      <Sidebar>
        <SidebarHeader>
          <span className="al-sidebar__brand">Nexus</span>
        </SidebarHeader>
        <SidebarContent>
          <SidebarGroup>
            {NAV_ITEMS.map(({ label, path, icon }) => (
              <SidebarItem
                key={path}
                href={path}
                active={isActive(path)}
                icon={icon}
                onClick={(e) => {
                  e.preventDefault();
                  void navigate({ to: path });
                }}
              >
                {label}
              </SidebarItem>
            ))}
          </SidebarGroup>
        </SidebarContent>
        <SidebarFooter>
          <SidebarCollapseButton />
        </SidebarFooter>
      </Sidebar>
      <Outlet />
    </AppShell>
  );
}
