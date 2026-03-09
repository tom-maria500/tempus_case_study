import React, { useState, useCallback } from 'react';
import { Routes, Route } from 'react-router-dom';
import { Sidebar } from './components/layout/Sidebar';
import { TopBar } from './components/layout/TopBar';
import { ProviderTable } from './components/providers/ProviderTable';
import { BriefPanel } from './components/brief/BriefPanel';
import { useBrief } from './hooks/useBrief';

function ProvidersPage({ onSelectProvider, onGenerateBrief, searchQuery }) {
  return (
    <div className="mx-auto flex w-full max-w-5xl flex-1 gap-4 px-6 py-5">
      <div className="flex-1 min-w-0">
        <ProviderTable
          onSelectProvider={onSelectProvider}
          onGenerateBrief={onGenerateBrief}
          searchQuery={searchQuery}
        />
      </div>
    </div>
  );
}

function App() {
  const [selectedProvider, setSelectedProvider] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [panelOpen, setPanelOpen] = useState(false);
  const { brief, isLoading, error, fetchBrief, invalidateBrief, refetchBrief } = useBrief();

  const handleProviderUpdate = useCallback(
    (result, physicianForRefetch) => {
      if (result?.physician_id) {
        if (result.new_priority_score != null) {
          setSelectedProvider((prev) =>
            prev?.physician_id === result.physician_id
              ? { ...prev, priority_score: result.new_priority_score }
              : prev
          );
        }
        if (physicianForRefetch?.physician_id === result.physician_id) {
          invalidateBrief(result.physician_id);
          refetchBrief(physicianForRefetch);
        }
      }
    },
    [invalidateBrief, refetchBrief]
  );

  const handleSelectProvider = (provider) => {
    setSelectedProvider(provider);
  };

  const handleGenerateBrief = (provider) => {
    const target = provider || selectedProvider;
    if (!target) return;
    setSelectedProvider(target);
    setPanelOpen(true);
    fetchBrief(target);
  };

  return (
    <div className="flex h-screen bg-bg-primary text-text-primary">
      <Sidebar active="providers" />
      <main className="flex min-w-0 flex-1 flex-col">
        <TopBar
          title="Provider Intelligence"
          onSearch={setSearchQuery}
        />
        <Routes>
          <Route
            path="/"
            element={
              <ProvidersPage
                onSelectProvider={handleSelectProvider}
                onGenerateBrief={handleGenerateBrief}
                searchQuery={searchQuery}
              />
            }
          />
        </Routes>
      </main>
      <BriefPanel
        open={panelOpen}
        onClose={() => setPanelOpen(false)}
        physician={selectedProvider}
        brief={brief}
        isLoading={isLoading}
        error={error}
        onProviderUpdate={handleProviderUpdate}
        onRefetchBrief={refetchBrief}
      />
    </div>
  );
}

export default App;

