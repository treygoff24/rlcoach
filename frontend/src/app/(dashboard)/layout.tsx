// frontend/src/app/(dashboard)/layout.tsx
'use client';

import { useState } from 'react';
import { SessionProvider } from 'next-auth/react';
import { Sidebar } from '@/components/layout/Sidebar';
import { Navbar } from '@/components/layout/Navbar';
import { UploadModal } from '@/components/layout/UploadModal';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { ToastProvider } from '@/components/Toast';
import { TosRecorder } from '@/components/TosRecorder';

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [uploadModalOpen, setUploadModalOpen] = useState(false);

  return (
    <SessionProvider>
      <TosRecorder />
      <ToastProvider>
        <div className="flex h-screen overflow-hidden noise">
          {/* Sidebar */}
          <Sidebar
            isOpen={sidebarOpen}
            onClose={() => setSidebarOpen(false)}
          />

          {/* Main content */}
          <div className="flex-1 flex flex-col overflow-hidden">
            {/* Navbar */}
            <Navbar
              onMenuClick={() => setSidebarOpen(true)}
              onUploadClick={() => setUploadModalOpen(true)}
            />

            {/* Page content with scroll */}
            <main className="flex-1 overflow-y-auto">
              <ErrorBoundary>
                {children}
              </ErrorBoundary>
            </main>
          </div>

          {/* Upload Modal */}
          <UploadModal
            isOpen={uploadModalOpen}
            onClose={() => setUploadModalOpen(false)}
          />
        </div>
      </ToastProvider>
    </SessionProvider>
  );
}
