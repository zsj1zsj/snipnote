import { Link, useLocation } from 'react-router-dom';
import { BookOpen, Star, Tag, Calendar, Clock, Plus, LayoutGrid } from 'lucide-react';
import { useState, useEffect } from 'react';
import api from '../api';

export default function Navbar() {
  const location = useLocation();
  const [stats, setStats] = useState({ total: 0, due: 0, favorites: 0 });

  useEffect(() => {
    api.getStats().then(setStats).catch(console.error);
  }, []);

  const isActive = (path) => location.pathname === path;

  const navItems = [
    { path: '/', icon: LayoutGrid, label: '首页' },
    { path: '/highlights', icon: BookOpen, label: '摘录' },
    { path: '/review', icon: Clock, label: '复习', badge: stats.due },
    { path: '/favorites', icon: Star, label: '收藏', badge: stats.favorites },
    { path: '/tags', icon: Tag, label: '标签' },
    { path: '/daily', icon: Calendar, label: '日报' },
  ];

  return (
    <nav className="navbar sticky top-0 z-50">
      <div className="max-w-5xl mx-auto flex items-center justify-between px-4 py-3">
        <div className="flex items-center gap-8">
          <Link
            to="/"
            className="text-xl font-bold text-gray-800 hover:text-gray-600 transition-colors"
          >
            SnipNote
          </Link>
          <div className="flex gap-1">
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
        <Link
          to="/add"
          className="btn btn-primary flex items-center gap-2"
        >
          <Plus size={16} />
          添加摘录
        </Link>
      </div>
    </nav>
  );
}
