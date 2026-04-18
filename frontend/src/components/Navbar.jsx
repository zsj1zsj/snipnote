import { Link, useLocation } from 'react-router-dom';
import { BookOpen, Star, Tag, Calendar, Clock, Plus, LayoutGrid, Rss, Headphones, Menu, X } from 'lucide-react';
import { useState, useEffect } from 'react';
import api from '../api';

export default function Navbar() {
  const location = useLocation();
  const [stats, setStats] = useState({ total: 0, due: 0, favorites: 0 });
  const [rssUnread, setRssUnread] = useState(0);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    api.getStats().then(setStats).catch(console.error);
    api.getRssUnreadCount().then(data => setRssUnread(data.count)).catch(console.error);
  }, []);

  // Close menu on route change
  useEffect(() => {
    setMenuOpen(false);
  }, [location.pathname]);

  // Close menu on Escape
  useEffect(() => {
    const handleKey = (e) => { if (e.key === 'Escape') setMenuOpen(false); };
    if (menuOpen) {
      document.addEventListener('keydown', handleKey);
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.removeEventListener('keydown', handleKey);
      document.body.style.overflow = '';
    };
  }, [menuOpen]);

  const isActive = (path) => location.pathname === path;

  const navItems = [
    { path: '/', icon: LayoutGrid, label: '首页' },
    { path: '/highlights', icon: BookOpen, label: '摘录' },
    { path: '/review', icon: Clock, label: '复习', badge: stats.due },
    { path: '/favorites', icon: Star, label: '收藏', badge: stats.favorites },
    { path: '/tags', icon: Tag, label: '标签' },
    { path: '/daily', icon: Calendar, label: '日报' },
    { path: '/rss', icon: Rss, label: 'RSS', badge: rssUnread },
    { path: '/podcast', icon: Headphones, label: 'Podcast' },
  ];

  return (
    <nav className="navbar sticky top-0 z-50">
      <div className="max-w-5xl mx-auto flex items-center justify-between px-4 py-3">
        <div className="flex items-center gap-4 md:gap-8">
          <Link
            to="/"
            className="text-xl font-bold text-gray-800 hover:text-gray-600 transition-colors"
          >
            SnipNote
          </Link>

          {/* Desktop nav */}
          <div className="hidden md:flex gap-1">
            {navItems.map((item) => (
              <Link
                key={item.path}
                to={item.path}
                className={`flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                  isActive(item.path)
                    ? 'bg-gray-900 text-white shadow-sm'
                    : 'text-gray-500 hover:bg-gray-100 hover:text-gray-800'
                }`}
              >
                <item.icon size={16} />
                {item.label}
                {item.badge > 0 && (
                  <span className="badge badge-red">
                    {item.badge}
                  </span>
                )}
              </Link>
            ))}
          </div>
        </div>

        {/* Desktop add button */}
        <Link
          to="/add-link"
          className="hidden md:flex btn btn-primary items-center gap-2"
        >
          <Plus size={16} />
          添加摘录
        </Link>

        {/* Mobile hamburger button */}
        <button
          onClick={() => setMenuOpen(!menuOpen)}
          className="md:hidden p-2.5 -mr-2 text-gray-600 hover:text-gray-900"
          aria-label="菜单"
        >
          {menuOpen ? <X size={22} /> : <Menu size={22} />}
        </button>
      </div>

      {/* Mobile drawer */}
      {menuOpen && (
        <div className="fixed inset-0 z-50 md:hidden">
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-black/30"
            onClick={() => setMenuOpen(false)}
          />
          {/* Panel */}
          <div className="absolute top-0 left-0 w-64 h-full bg-white shadow-xl flex flex-col">
            <div className="flex items-center justify-between px-4 py-4 border-b border-gray-100">
              <span className="text-lg font-bold text-gray-800">SnipNote</span>
              <button
                onClick={() => setMenuOpen(false)}
                className="p-2 text-gray-400 hover:text-gray-600"
              >
                <X size={20} />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto py-2">
              {navItems.map((item) => (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`flex items-center gap-3 px-5 py-3.5 text-base font-medium transition-colors ${
                    isActive(item.path)
                      ? 'bg-gray-100 text-gray-900'
                      : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                  }`}
                >
                  <item.icon size={20} />
                  {item.label}
                  {item.badge > 0 && (
                    <span className="badge badge-red ml-auto">
                      {item.badge}
                    </span>
                  )}
                </Link>
              ))}
            </div>
            <div className="p-4 border-t border-gray-100">
              <Link
                to="/add-link"
                className="btn btn-primary flex items-center justify-center gap-2 w-full"
              >
                <Plus size={16} />
                添加摘录
              </Link>
            </div>
          </div>
        </div>
      )}
    </nav>
  );
}
