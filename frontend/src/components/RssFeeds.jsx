import { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { Rss, Plus, Trash2, RefreshCw, Loader, ExternalLink, Upload, Download, Edit3, Check, X, AlertTriangle, FolderOpen } from 'lucide-react';
import api from '../api';
import { getCache, setCache, clearCache } from '../hooks/useCache';

const CACHE_KEY = 'rss_feeds';

function FeedFavicon({ siteUrl, size = 16 }) {
  const [error, setError] = useState(false);
  if (!siteUrl || error) {
    return <Rss size={size} className="text-orange-400 flex-shrink-0" />;
  }
  try {
    const host = new URL(siteUrl).origin;
    return (
      <img
        src={`${host}/favicon.ico`}
        alt=""
        width={size}
        height={size}
        className="flex-shrink-0 rounded"
        onError={() => setError(true)}
        referrerPolicy="no-referrer"
      />
    );
  } catch {
    return <Rss size={size} className="text-orange-400 flex-shrink-0" />;
  }
}

export default function RssFeeds() {
  const [feeds, setFeeds] = useState(() => getCache(CACHE_KEY) || []);
  const [url, setUrl] = useState('');
  const [category, setCategory] = useState('');
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [editingId, setEditingId] = useState(null);
  const [editTitle, setEditTitle] = useState('');
  const [editCategory, setEditCategory] = useState('');
  const [categories, setCategories] = useState([]);
  const [filterCategory, setFilterCategory] = useState('');
  const fileInputRef = useRef(null);

  const loadFeeds = async () => {
    try {
      const data = await api.getRssFeeds();
      setFeeds(data);
      setCache(CACHE_KEY, data);
      const cats = [...new Set(data.map(f => f.category).filter(Boolean))].sort();
      setCategories(cats);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    loadFeeds();
  }, []);

  const handleSubscribe = async () => {
    if (!url.trim()) return;
    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await api.addRssFeed(url.trim(), category.trim());
      if (result.already_subscribed) {
        setError('已经订阅过该源');
      } else {
        setSuccess(`已订阅「${result.title}」，获取了 ${result.new_articles} 篇文章`);
        setUrl('');
        setCategory('');
        loadFeeds();
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (feedId) => {
    if (!confirm('确定要退订该 RSS 源吗？所有文章也会被删除。')) return;
    try {
      await api.deleteRssFeed(feedId);
      loadFeeds();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleRefreshAll = async () => {
    setRefreshing(true);
    setError(null);
    try {
      const result = await api.refreshRss();
      const total = Object.values(result.results).reduce((a, b) => a + b, 0);
      setSuccess(`刷新完成，共获取 ${total} 篇新文章`);
      clearCache('rss_articles');
      loadFeeds();
    } catch (err) {
      setError(err.message);
    } finally {
      setRefreshing(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') handleSubscribe();
  };

  const startEdit = (feed) => {
    setEditingId(feed.id);
    setEditTitle(feed.title);
    setEditCategory(feed.category || '');
  };

  const saveEdit = async (feedId) => {
    try {
      await api.updateRssFeed(feedId, { title: editTitle, category: editCategory });
      setEditingId(null);
      loadFeeds();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleExportOpml = () => {
    window.open(api.exportRssOpml(), '_blank');
  };

  const handleImportOpml = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setError(null);
    try {
      const text = await file.text();
      const result = await api.importRssOpml(text);
      setSuccess(`正在导入 ${result.count} 个订阅源...`);
      setTimeout(loadFeeds, 3000);
    } catch (err) {
      setError(err.message);
    }
    e.target.value = '';
  };

  const filteredFeeds = filterCategory
    ? feeds.filter(f => f.category === filterCategory)
    : feeds;

  const groupedFeeds = {};
  filteredFeeds.forEach(f => {
    const cat = f.category || '';
    if (!groupedFeeds[cat]) groupedFeeds[cat] = [];
    groupedFeeds[cat].push(f);
  });
  const sortedCategories = Object.keys(groupedFeeds).sort((a, b) => {
    if (a === '') return 1;
    if (b === '') return -1;
    return a.localeCompare(b);
  });

  const renderFeed = (feed) => (
    <div key={feed.id} className="card p-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
      <div className="flex items-center gap-3 sm:gap-4 flex-1 min-w-0">
        <FeedFavicon siteUrl={feed.site_url} size={20} />
        <div className="flex-1 min-w-0">
          {editingId === feed.id ? (
            <div className="space-y-2">
              <input
                type="text"
                value={editTitle}
                onChange={(e) => setEditTitle(e.target.value)}
                className="input text-sm w-full"
                placeholder="标题"
                autoFocus
              />
              <div className="flex gap-2">
                <input
                  type="text"
                  value={editCategory}
                  onChange={(e) => setEditCategory(e.target.value)}
                  className="input text-sm flex-1"
                  placeholder="分组（可选）"
                  list="category-list"
                />
                <button onClick={() => saveEdit(feed.id)} className="text-green-500 hover:text-green-700 p-2.5">
                  <Check size={16} />
                </button>
                <button onClick={() => setEditingId(null)} className="text-gray-400 hover:text-gray-600 p-2.5">
                  <X size={16} />
                </button>
              </div>
            </div>
          ) : (
            <>
              <div className="font-medium text-gray-800 truncate flex items-center gap-2">
                {feed.title}
                {feed.error_count > 0 && (
                  <span className="text-amber-500" title={`连续 ${feed.error_count} 次获取失败: ${feed.last_error}`}>
                    <AlertTriangle size={14} />
                  </span>
                )}
              </div>
              <div className="text-sm text-gray-400 truncate">{feed.url}</div>
              <div className="text-xs text-gray-400 mt-1 flex items-center gap-2 flex-wrap">
                <span>{feed.total_articles} 篇文章 · {feed.unread_articles} 篇未读</span>
                {feed.last_fetched_at && <span>· 最后刷新 {feed.last_fetched_at.split('T')[0]}</span>}
                {feed.category && (
                  <span className="tag tag-blue text-xs">{feed.category}</span>
                )}
              </div>
            </>
          )}
        </div>
      </div>
      {editingId !== feed.id && (
        <div className="flex items-center gap-2 self-end sm:self-auto">
          <Link
            to={`/rss/articles?feed_id=${feed.id}`}
            className="btn btn-secondary text-sm px-3 py-1.5"
          >
            查看文章
          </Link>
          <button
            onClick={() => startEdit(feed)}
            className="text-gray-400 hover:text-gray-600 p-2.5"
            title="编辑"
          >
            <Edit3 size={16} />
          </button>
          {feed.site_url && (
            <a
              href={feed.site_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-gray-400 hover:text-gray-600 p-2.5"
              title="访问网站"
            >
              <ExternalLink size={16} />
            </a>
          )}
          <button
            onClick={() => handleDelete(feed.id)}
            className="text-gray-400 hover:text-red-500 p-2.5"
            title="退订"
          >
            <Trash2 size={16} />
          </button>
        </div>
      )}
    </div>
  );

  return (
    <div className="page-container max-w-3xl">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between mb-6">
        <h1 className="page-title mb-0">RSS 订阅</h1>
        <div className="flex flex-wrap gap-2">
          <Link to="/rss/articles" className="btn btn-secondary flex items-center gap-2">
            <span className="hidden sm:inline">文章列表</span>
            <span className="sm:hidden text-sm">文章</span>
          </Link>
          <button
            onClick={handleExportOpml}
            disabled={feeds.length === 0}
            className="btn btn-secondary flex items-center gap-2"
            title="导出 OPML"
          >
            <Download size={16} />
          </button>
          <button
            onClick={() => fileInputRef.current?.click()}
            className="btn btn-secondary flex items-center gap-2"
            title="导入 OPML"
          >
            <Upload size={16} />
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".opml,.xml"
            className="hidden"
            onChange={handleImportOpml}
          />
          <button
            onClick={handleRefreshAll}
            disabled={refreshing || feeds.length === 0}
            className="btn btn-secondary flex items-center gap-2"
          >
            <RefreshCw size={16} className={refreshing ? 'animate-spin' : ''} />
            <span className="hidden sm:inline">刷新全部</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-600 px-4 py-3 rounded-lg mb-4">
          {error}
        </div>
      )}
      {success && (
        <div className="bg-green-50 border border-green-200 text-green-600 px-4 py-3 rounded-lg mb-4">
          {success}
        </div>
      )}

      <div className="flex flex-col gap-3 sm:flex-row mb-4">
        <input
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入 RSS 源地址..."
          className="input flex-1"
          autoFocus
        />
        <input
          type="text"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          placeholder="分组（可选）"
          className="input w-full sm:w-32"
          list="category-list"
        />
        <datalist id="category-list">
          {categories.map(c => <option key={c} value={c} />)}
        </datalist>
        <button
          onClick={handleSubscribe}
          disabled={loading || !url.trim()}
          className="btn btn-primary flex items-center justify-center gap-2 w-full sm:w-auto sm:px-6"
        >
          {loading ? <Loader size={18} className="animate-spin" /> : <Plus size={18} />}
          订阅
        </button>
      </div>

      {categories.length > 0 && (
        <div className="flex gap-1 mb-6 flex-wrap">
          <button
            onClick={() => setFilterCategory('')}
            className={`px-3 py-2 rounded-lg text-sm font-medium transition-all ${
              filterCategory === '' ? 'bg-gray-900 text-white' : 'text-gray-500 hover:bg-gray-100'
            }`}
          >
            全部
          </button>
          {categories.map(cat => (
            <button
              key={cat}
              onClick={() => setFilterCategory(cat)}
              className={`px-3 py-2 rounded-lg text-sm font-medium transition-all flex items-center gap-1 ${
                filterCategory === cat ? 'bg-gray-900 text-white' : 'text-gray-500 hover:bg-gray-100'
              }`}
            >
              <FolderOpen size={14} />
              {cat}
            </button>
          ))}
        </div>
      )}

      {feeds.length === 0 ? (
        <div className="card p-8 text-center text-gray-400 text-sm">
          <Rss size={40} className="mx-auto mb-3 text-gray-300" />
          还没有订阅任何 RSS 源，输入地址开始订阅
        </div>
      ) : (
        <div className="space-y-3">
          {sortedCategories.map(cat => (
            <div key={cat || '__uncategorized'}>
              {cat && categories.length > 0 && !filterCategory && (
                <div className="flex items-center gap-2 text-sm text-gray-500 font-medium mt-4 mb-2">
                  <FolderOpen size={14} />
                  {cat}
                </div>
              )}
              <div className="space-y-3">
                {groupedFeeds[cat].map(renderFeed)}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
