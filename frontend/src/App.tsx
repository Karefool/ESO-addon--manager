import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Search, Compass, Package, Settings, Download, X, RefreshCw, HardDrive, Trash2 } from 'lucide-react';
import { parseBBCode, stripBBCode } from './bbcode';
import './index.css';

const API_BASE = '/api';

interface Category {
  id: string;
  title: string;
  file_count: number;
}

interface Addon {
  id: string;
  name: string;
  author_name: string;
  download_total: number;
  description: string;
  version: string;
  is_installed: boolean;
  directories: string;
}

interface UpdateInfo {
  update_available: boolean;
  latest_version: string;
  download_url: string;
  current_version: string;
}

function App() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [addons, setAddons] = useState<Addon[]>([]);
  const [installed, setInstalled] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  const [search, setSearch] = useState('');
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const [sort, setSort] = useState('download_total');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  const [installingId, setInstallingId] = useState<string | null>(null);
  const [uninstallingName, setUninstallingName] = useState<string | null>(null);
  const [view, setView] = useState<'discover' | 'installed' | 'settings'>('discover');
  const [selectedAddon, setSelectedAddon] = useState<Addon | null>(null);
  const [updateInfo, setUpdateInfo] = useState<UpdateInfo | null>(null);
  const [updateDismissed, setUpdateDismissed] = useState(false);

  useEffect(() => {
    fetchCategories();
    fetchInstalled();
    checkForUpdate();

    const handleFocus = () => {
      fetchInstalled();
      if (view === 'discover') fetchAddons();
    };

    window.addEventListener('focus', handleFocus);
    return () => window.removeEventListener('focus', handleFocus);
  }, []);

  useEffect(() => {
    if (view === 'discover') {
      fetchAddons();
    }
  }, [search, activeCategory, sort, page, view]);

  const fetchCategories = async () => {
    try {
      const res = await fetch(`${API_BASE}/categories`);
      const data = await res.json();
      setCategories(data);
    } catch (err) {
      console.error('Failed to fetch categories:', err);
    }
  };

  const fetchInstalled = async () => {
    try {
      const res = await fetch(`${API_BASE}/installed`);
      const data = await res.json();
      setInstalled(data.installed);
    } catch (err) {
      console.error('Failed to fetch installed addons:', err);
    }
  };

  const fetchAddons = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        page: page.toString(),
        limit: '20',
        sort_by: sort,
        order: 'desc'
      });
      if (search) params.append('query', search);
      if (activeCategory) params.append('category_id', activeCategory);

      const res = await fetch(`${API_BASE}/addons?${params}`);
      const data = await res.json();
      setAddons(data.addons);
      setTotalPages(Math.ceil(data.total / data.limit));
    } catch (err) {
      console.error('Failed to fetch addons:', err);
    } finally {
      setLoading(false);
    }
  };

  const checkForUpdate = async () => {
    try {
      const res = await fetch(`${API_BASE}/check-update`);
      const data: UpdateInfo = await res.json();
      if (data.update_available) {
        setUpdateInfo(data);
      }
    } catch (err) {
      // Non-critical, ignore
    }
  };

  const installAddon = async (id: string, name: string) => {
    setInstallingId(id);
    try {
      const res = await fetch(`${API_BASE}/install/${id}`, { method: 'POST' });
      if (res.ok) {
        fetchInstalled();
        setAddons(prev => prev.map(a => a.id === id ? { ...a, is_installed: true } : a));
        if (selectedAddon?.id === id) {
          setSelectedAddon(prev => prev ? { ...prev, is_installed: true } : null);
        }
      } else {
        alert(`Failed to install ${name}`);
      }
    } catch (err) {
      alert(`Error installing ${name}`);
    } finally {
      setInstallingId(null);
    }
  };

  const uninstallAddon = async (dirName: string) => {
    if (!window.confirm(`Are you sure you want to uninstall "${dirName}"? This will delete the addon folder.`)) {
      return;
    }

    setUninstallingName(dirName);
    try {
      const res = await fetch(`${API_BASE}/uninstall/${dirName}`, { method: 'DELETE' });
      if (res.ok) {
        fetchInstalled();
        // Refresh addon list to update is_installed flags
        if (view === 'discover') fetchAddons();
        if (selectedAddon) {
          setSelectedAddon(prev => prev ? { ...prev, is_installed: false } : null);
        }
      } else {
        const data = await res.json();
        alert(`Failed to uninstall: ${data.detail || 'Unknown error'}`);
      }
    } catch (err) {
      alert(`Error uninstalling ${dirName}`);
    } finally {
      setUninstallingName(null);
    }
  };

  return (
    <div className="flex h-screen w-full bg-[#09090b] text-zinc-100 overflow-hidden font-sans selection:bg-blue-500/30">

      {/* Sidebar */}
      <aside className="w-64 border-r border-white/5 bg-[#09090b]/80 backdrop-blur-xl flex flex-col z-20 sticky top-0">
        <div className="p-6">
          <h1 className="text-xl font-bold tracking-tighter bg-gradient-to-br from-white to-white/50 bg-clip-text text-transparent flex items-center gap-2">
            <Package className="w-5 h-5 text-blue-500" />
            ESO Power Lite
          </h1>
        </div>

        <nav className="flex-1 px-4 space-y-1">
          <button
            onClick={() => setView('discover')}
            className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 ${
              view === 'discover'
                ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20 shadow-[0_0_15px_rgba(59,130,246,0.1)]'
                : 'text-zinc-400 hover:text-zinc-100 hover:bg-white/5'
            }`}
          >
            <Compass className="w-4 h-4" /> Discover Addons
          </button>

          <button
            onClick={() => setView('installed')}
            className={`w-full flex flex-row justify-between items-center px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 ${
              view === 'installed'
                ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20 shadow-[0_0_15px_rgba(59,130,246,0.1)]'
                : 'text-zinc-400 hover:text-zinc-100 hover:bg-white/5'
            }`}
          >
            <span className="flex items-center gap-3"><HardDrive className="w-4 h-4" /> My Addons</span>
            {installed.length > 0 && (
              <span className="bg-white/10 text-zinc-300 text-xs py-0.5 px-2 rounded-full border border-white/5">
                {installed.length}
              </span>
            )}
          </button>

          <div className="pt-6 pb-2">
            <p className="text-xs font-semibold text-zinc-600 uppercase tracking-wider px-3">Categories</p>
          </div>
          <div className="space-y-0.5 max-h-[40vh] overflow-y-auto pr-1 pb-4 custom-scroll">
            <button
              onClick={() => { setActiveCategory(null); setPage(1); setView('discover'); }}
              className={`w-full text-left px-3 py-1.5 rounded-md text-sm transition-colors ${
                !activeCategory && view === 'discover' ? 'text-zinc-100 bg-white/5' : 'text-zinc-500 hover:text-zinc-300 hover:bg-white/5'
              }`}
            >
              All Categories
            </button>
            {categories.map(c => (
              <button
                key={c.id}
                onClick={() => { setActiveCategory(c.id); setPage(1); setView('discover'); }}
                className={`w-full flex justify-between items-center px-3 py-1.5 rounded-md text-sm transition-colors ${
                  activeCategory === c.id && view === 'discover' ? 'text-zinc-100 bg-white/5' : 'text-zinc-500 hover:text-zinc-300 hover:bg-white/5'
                }`}
              >
                <span className="truncate pr-2">{c.title}</span>
                <span className="text-xs opacity-50">{c.file_count}</span>
              </button>
            ))}
          </div>
        </nav>

        <div className="p-4 border-t border-white/5">
          <button
            onClick={() => setView('settings')}
            className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 ${
              view === 'settings'
              ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20 shadow-[0_0_15px_rgba(59,130,246,0.1)]'
              : 'text-zinc-400 hover:text-zinc-100 hover:bg-white/5'
            }`}
          >
            <Settings className="w-4 h-4" /> Settings
          </button>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col min-w-0 bg-gradient-to-br from-[#09090b] to-[#0c0c10] relative">
        <div className="absolute inset-0 bg-[url('https://grainy-gradients.vercel.app/noise.svg')] opacity-20 brightness-100 contrast-150 mix-blend-overlay pointer-events-none z-0"></div>

        {/* Update Banner */}
        {updateInfo && !updateDismissed && (
          <div className="relative z-20 bg-blue-600/20 border-b border-blue-500/30 px-8 py-2.5 flex items-center justify-between">
            <p className="text-sm text-blue-200">
              New version <strong>v{updateInfo.latest_version}</strong> is available (you have v{updateInfo.current_version}).
              <a
                href={updateInfo.download_url}
                target="_blank"
                rel="noopener noreferrer"
                className="ml-2 underline text-blue-300 hover:text-white transition-colors"
                onClick={(e) => {
                  e.preventDefault();
                  window.open(updateInfo.download_url, '_blank');
                }}
              >
                Download update
              </a>
            </p>
            <button
              onClick={() => setUpdateDismissed(true)}
              className="text-blue-300 hover:text-white transition-colors p-1"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* Topbar */}
        <header className="h-16 border-b border-white/5 bg-white/[0.02] backdrop-blur-md flex items-center justify-between px-8 z-10 shrink-0">
          <div className="w-full max-w-md relative">
            {view === 'discover' && (
              <>
                <Search className="w-4 h-4 absolute left-3 text-zinc-500 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  placeholder="Search addons..."
                  className="w-full bg-zinc-900/50 border border-white/10 rounded-full py-1.5 pl-10 pr-4 text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/50 transition-all shadow-inner"
                  value={search}
                  onChange={(e) => {
                    setSearch(e.target.value);
                    setPage(1);
                  }}
                />
              </>
            )}
          </div>

          <div className="flex items-center gap-4">
            <button
              onClick={() => { fetchInstalled(); if(view==='discover') fetchAddons(); }}
              className="text-zinc-400 hover:text-zinc-100 transition-colors p-2"
              title="Refresh Local Files"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        </header>

        {/* Scrollable Content */}
        <div className="flex-1 overflow-y-auto p-8 relative z-10 custom-scroll">

          {view === 'discover' && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="max-w-7xl mx-auto">
              <div className="flex justify-between items-end mb-8">
                <div>
                  <h2 className="text-3xl font-bold tracking-tight text-zinc-100">Discover</h2>
                  <p className="text-sm text-zinc-400 mt-1">Browse and install the best addons for Elder Scrolls Online.</p>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-zinc-500 font-medium uppercase tracking-wider">Sort by</span>
                  <select
                    value={sort}
                    onChange={(e) => { setSort(e.target.value); setPage(1); }}
                    className="bg-zinc-900 border border-white/10 rounded-lg py-1.5 px-3 text-sm text-zinc-300 focus:outline-none focus:border-blue-500 sm:text-sm"
                  >
                    <option value="download_total">Most Downloaded</option>
                    <option value="last_updated">Recently Updated</option>
                    <option value="favorite_total">Most Favorited</option>
                  </select>
                </div>
              </div>

              {loading ? (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 animate-pulse">
                  {[...Array(12)].map((_, i) => (
                    <div key={i} className="h-[220px] rounded-xl bg-white/5 border border-white/5"></div>
                  ))}
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                  {addons.map((addon, i) => (
                    <motion.div
                      initial={{ opacity: 0, scale: 0.95 }}
                      animate={{ opacity: 1, scale: 1 }}
                      transition={{ delay: i * 0.05 }}
                      key={addon.id}
                      onClick={() => setSelectedAddon(addon)}
                      className="group relative flex flex-col bg-white/[0.02] border border-white/5 rounded-xl p-5 hover:bg-white/[0.04] hover:border-white/10 transition-all cursor-pointer overflow-hidden shadow-lg shadow-black/20"
                    >
                      <div className="absolute inset-0 bg-gradient-to-tr from-blue-500/0 via-blue-500/0 to-blue-500/5 opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>

                      <div className="flex-1">
                        <h3 className="text-base font-semibold text-zinc-100 line-clamp-1 group-hover:text-blue-400 transition-colors" dangerouslySetInnerHTML={{ __html: addon.name }} />
                        <p className="text-xs text-zinc-500 mt-0.5 mb-3">by {addon.author_name}</p>
                        <p className="text-sm text-zinc-400 line-clamp-3 leading-relaxed">{stripBBCode(addon.description) || "No description available."}</p>
                      </div>

                      <div className="mt-5 flex items-center justify-between pt-4 border-t border-white/5 relative z-10">
                        <div className="flex items-center gap-1.5 text-xs text-zinc-500">
                          <Download className="w-3.5 h-3.5" />
                          <span>{(addon.download_total / 1000).toFixed(1)}k</span>
                        </div>

                        {addon.is_installed ? (
                          <div className="flex items-center gap-2">
                            <span className="px-2 py-1 rounded-md text-xs font-medium bg-green-500/10 text-green-400 border border-green-500/20">
                              Installed
                            </span>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                const dirs = addon.directories ? addon.directories.split(',') : [];
                                const matchedDir = dirs.find(d => installed.includes(d));
                                if (matchedDir) {
                                  uninstallAddon(matchedDir);
                                } else {
                                  alert('Could not determine addon directory. Please uninstall from My Addons tab.');
                                }
                              }}
                              className="p-1 rounded-md text-zinc-500 hover:text-red-400 hover:bg-red-400/10 transition-colors"
                              title="Uninstall"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        ) : (
                          <button
                            disabled={installingId === addon.id}
                            onClick={(e) => {
                              e.stopPropagation();
                              installAddon(addon.id, addon.name);
                            }}
                            className="px-3 py-1 rounded-md text-xs font-medium bg-white/10 text-zinc-100 hover:bg-blue-600 hover:text-white transition-colors border border-white/5 disabled:opacity-50"
                          >
                            {installingId === addon.id ? 'Loading...' : 'Install'}
                          </button>
                        )}
                      </div>
                    </motion.div>
                  ))}
                </div>
              )}

              {!loading && totalPages > 1 && (
                <div className="flex items-center justify-center gap-4 mt-12 mb-8">
                  <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1} className="px-4 py-2 rounded-lg bg-zinc-900 border border-white/10 text-sm text-zinc-300 hover:bg-white/5 disabled:opacity-50 transition-colors">Previous</button>
                  <span className="text-sm text-zinc-500">Page <strong className="text-zinc-300">{page}</strong> of <strong className="text-zinc-300">{totalPages}</strong></span>
                  <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages} className="px-4 py-2 rounded-lg bg-zinc-900 border border-white/10 text-sm text-zinc-300 hover:bg-white/5 disabled:opacity-50 transition-colors">Next</button>
                </div>
              )}
            </motion.div>
          )}

          {view === 'installed' && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="max-w-5xl mx-auto">
              <div className="flex justify-between items-end mb-8">
                <div>
                  <h2 className="text-3xl font-bold tracking-tight text-zinc-100">My Addons</h2>
                  <p className="text-sm text-zinc-400 mt-1">Addons synced with your local AddOns folder.</p>
                </div>
              </div>

              {installed.length === 0 ? (
                <div className="text-center py-20 px-4 border border-white/5 border-dashed rounded-2xl bg-white/[0.01]">
                  <HardDrive className="w-12 h-12 text-zinc-600 mx-auto mb-4" />
                  <h3 className="text-lg font-medium text-zinc-300">No addons found</h3>
                  <p className="text-sm text-zinc-500 mt-1">Install some addons from the Discover tab to see them here.</p>
                </div>
              ) : (
                <div className="bg-[#0c0c10] border border-white/10 rounded-2xl overflow-hidden shadow-2xl">
                  <table className="w-full text-left text-sm whitespace-nowrap">
                    <thead className="lowercase text-zinc-500 bg-white/5 border-b border-white/10">
                      <tr>
                        <th className="px-6 py-4 font-medium tracking-wider">Directory Name</th>
                        <th className="px-6 py-4 font-medium tracking-wider">Status</th>
                        <th className="px-6 py-4 font-medium tracking-wider text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5">
                      {installed.map((name) => (
                        <tr key={name} className="hover:bg-white/[0.02] transition-colors">
                          <td className="px-6 py-4">
                            <div className="flex items-center gap-3">
                              <div className="w-8 h-8 rounded bg-white/10 flex items-center justify-center flex-shrink-0">
                                <Package className="w-4 h-4 text-zinc-400" />
                              </div>
                              <span className="font-medium text-zinc-200">{name}</span>
                            </div>
                          </td>
                          <td className="px-6 py-4">
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-green-500/10 text-green-400 border border-green-500/20">
                              <span className="w-1.5 h-1.5 rounded-full bg-green-500"></span> Installed
                            </span>
                          </td>
                          <td className="px-6 py-4 text-right">
                            <button
                              onClick={() => uninstallAddon(name)}
                              disabled={uninstallingName === name}
                              className="text-zinc-500 hover:text-red-400 transition-colors text-xs font-medium px-2 py-1 rounded hover:bg-red-400/10 disabled:opacity-50"
                            >
                              {uninstallingName === name ? 'Removing...' : 'Uninstall'}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </motion.div>
          )}

          {view === 'settings' && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="max-w-2xl mx-auto">
              <h2 className="text-3xl font-bold tracking-tight text-zinc-100 mb-8">Settings</h2>

              <div className="space-y-6">
                <div className="bg-[#0c0c10] border border-white/10 rounded-2xl p-6 shadow-xl">
                  <h3 className="text-lg font-medium text-zinc-200 mb-4">Installation Directory</h3>
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-zinc-400">ESO AddOns Path</label>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        readOnly
                        value="~\Documents\Elder Scrolls Online\live\AddOns"
                        className="flex-1 bg-zinc-900 border border-white/10 rounded-lg py-2 px-3 text-sm text-zinc-400 focus:outline-none focus:border-blue-500/50"
                      />
                      <button className="px-4 py-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 transition-colors text-sm font-medium text-zinc-200 border border-white/5">
                        Browse
                      </button>
                    </div>
                    <p className="text-xs text-zinc-500 mt-2">This is where your Addons will be installed natively.</p>
                  </div>
                </div>

                <div className="bg-[#0c0c10] border border-white/10 rounded-2xl p-6 shadow-xl">
                  <h3 className="text-lg font-medium text-zinc-200 mb-4">App Preferences</h3>
                  <div className="flex items-center justify-between py-3">
                    <div>
                      <h4 className="text-sm font-medium text-zinc-300">Backups</h4>
                      <p className="text-xs text-zinc-500 mt-0.5">Create a backup of SavedVariables before updating.</p>
                    </div>
                    <div className="w-10 h-6 bg-zinc-800 border border-white/5 rounded-full cursor-pointer relative shadow-inner">
                      <div className="absolute left-1 top-1 w-4 h-4 bg-zinc-400 rounded-full shadow-sm"></div>
                    </div>
                  </div>
                </div>
              </div>
            </motion.div>
          )}

        </div>
      </main>

      {/* Modal / Dialog for Addon Details */}
      <AnimatePresence>
        {selectedAddon && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-black/80 backdrop-blur-sm"
            onClick={() => setSelectedAddon(null)}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              transition={{ type: "spring", damping: 25, stiffness: 300 }}
              className="bg-[#0c0c10] border border-white/10 rounded-2xl shadow-2xl w-full max-w-2xl max-h-[85vh] flex flex-col overflow-hidden"
              onClick={e => e.stopPropagation()}
            >
              <div className="px-6 py-5 border-b border-white/5 flex justify-between items-start shrink-0 bg-white/[0.01]">
                <div>
                  <h2 className="text-2xl font-bold text-zinc-100 flex items-center gap-3">
                    <span dangerouslySetInnerHTML={{ __html: selectedAddon.name }} />
                    {selectedAddon.is_installed && (
                       <span className="px-2 py-0.5 rounded text-xs font-medium bg-green-500/10 text-green-400 border border-green-500/20">Installed</span>
                    )}
                  </h2>
                  <div className="flex items-center gap-4 mt-2 text-sm text-zinc-400">
                    <span>by <strong className="text-zinc-200">{selectedAddon.author_name}</strong></span>
                    <span className="w-1 h-1 rounded-full bg-zinc-700"></span>
                    <span>Version {selectedAddon.version}</span>
                    <span className="w-1 h-1 rounded-full bg-zinc-700"></span>
                    <span className="flex items-center gap-1"><Download className="w-3.5 h-3.5" /> {(selectedAddon.download_total / 1000).toFixed(1)}k</span>
                  </div>
                </div>
                <button
                  onClick={() => setSelectedAddon(null)}
                  className="p-1.5 rounded-md hover:bg-white/10 text-zinc-400 hover:text-white transition-colors"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              <div className="flex-1 overflow-y-auto p-6 text-zinc-300 text-sm leading-relaxed prose prose-invert max-w-none custom-scroll" style={{ whiteSpace: 'pre-line' }}>
                <span dangerouslySetInnerHTML={{ __html: parseBBCode(selectedAddon.description) }} />
              </div>

              <div className="px-6 py-4 border-t border-white/5 bg-zinc-900/50 shrink-0 flex justify-between items-center">
                <span className="text-xs text-zinc-500">Addon ID: {selectedAddon.id}</span>

                {selectedAddon.is_installed ? (
                  <button
                    onClick={() => {
                      const dirs = selectedAddon.directories ? selectedAddon.directories.split(',') : [];
                      const matchedDir = dirs.find(d => installed.includes(d));
                      if (matchedDir) {
                        uninstallAddon(matchedDir);
                      } else {
                        alert('Could not determine addon directory. Please uninstall from My Addons tab.');
                      }
                    }}
                    className="flex items-center gap-2 px-6 py-2.5 rounded-lg font-medium text-sm bg-red-500/10 hover:bg-red-500/20 text-red-400 transition-all border border-red-500/20"
                  >
                    <Trash2 className="w-4 h-4" /> Uninstall
                  </button>
                ) : (
                  <button
                    disabled={installingId === selectedAddon.id}
                    onClick={() => installAddon(selectedAddon.id, selectedAddon.name)}
                    className="flex items-center gap-2 px-6 py-2.5 rounded-lg font-medium text-sm bg-blue-600 hover:bg-blue-500 text-white transition-all shadow-lg shadow-blue-500/20 disabled:opacity-50"
                  >
                    {installingId === selectedAddon.id ? (
                      <>
                        <RefreshCw className="w-4 h-4 animate-spin" /> Installing...
                      </>
                    ) : (
                      <>
                        <Download className="w-4 h-4" /> Install Now
                      </>
                    )}
                  </button>
                )}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

    </div>
  );
}

export default App;
