import { Link } from 'react-router-dom';
import { Star, Check, Trash2, BookOpen, Download } from 'lucide-react';
import { useState } from 'react';
import api from '../api';
import { exportHighlightAsMarkdown } from '../exportMarkdown';

export default function HighlightCard({ highlight, onUpdate, onDelete }) {
  const [loading, setLoading] = useState(false);

  const handleToggleFavorite = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    setLoading(true);
    try {
      const updated = await api.toggleFavorite(highlight.id);
      onUpdate?.(updated);
    } catch (err) {
      console.error('Failed to toggle favorite:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleToggleRead = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    setLoading(true);
    try {
      const updated = await api.toggleRead(highlight.id);
      onUpdate?.(updated);
    } catch (err) {
      console.error('Failed to toggle read:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (!confirm('确定要删除这条摘录吗？')) return;
    setLoading(true);
    try {
      await api.deleteHighlight(highlight.id);
      onDelete?.(highlight.id);
    } catch (err) {
      console.error('Failed to delete:', err);
    } finally {
      setLoading(false);
    }
  };

  const tags = highlight.tags
    ? highlight.tags.split(',').map((t) => t.trim()).filter(Boolean)
    : [];

  // Strip markdown syntax for plain-text preview
  const stripMarkdown = (text) => {
    if (!text) return '';
    let s = text;
    s = s.replace(/```[\s\S]*?```/g, ' ');        // fenced code blocks
    s = s.replace(/!\[[^\]]*\]\([^)]*\)/g, '');    // images
    s = s.replace(/\[([^\]]*)\]\([^)]*\)/g, '$1'); // links → text only
    s = s.replace(/^#{1,6}\s+/gm, '');             // headings
    s = s.replace(/(\*\*|__)(.*?)\1/g, '$2');      // bold
    s = s.replace(/(\*|_)(.*?)\1/g, '$2');         // italic
    s = s.replace(/`([^`]+)`/g, '$1');             // inline code
    s = s.replace(/\n{2,}/g, '\n');                // collapse blank lines
    return s.trim();
  };

  // Display summary if available, otherwise first 300 chars of cleaned text
  const cleanText = stripMarkdown(highlight.summary || highlight.text || '');
  const displayContent = cleanText.slice(0, 300) + (cleanText.length > 300 ? '...' : '');

  return (
    <Link
      to={`/highlight/${highlight.id}`}
      className="highlight-card block group"
    >
      <div className="min-w-0">
        {/* Source and meta */}
        <div className="flex items-center gap-2 text-sm text-gray-400 mb-3 min-w-0">
          {highlight.source ? (
            <>
              <BookOpen size={14} className="flex-shrink-0" />
              <span className="truncate font-medium">{highlight.source}</span>
              {highlight.author && (
                <span className="text-gray-400 truncate hidden sm:inline">- {highlight.author}</span>
              )}
            </>
          ) : null}
          {highlight.next_review && highlight.next_review <= new Date().toISOString().split('T')[0] && (
            <span className="tag tag-red text-xs ml-auto flex-shrink-0">
              待复习
            </span>
          )}
          {highlight.is_read === 1 && (
            <span className="tag tag-green text-xs flex-shrink-0">
              已读
            </span>
          )}
        </div>

        {/* Text content - summary or first 300 chars */}
        <div className="text-content mb-4">
          {displayContent}
        </div>

        {/* Tags + Actions */}
        <div className="flex items-center justify-between gap-2">
          {/* Tags */}
          <div className="flex flex-wrap gap-1.5 min-w-0">
            {tags.map((tag) => (
              <span key={tag} className="tag tag-gray">
                #{tag}
              </span>
            ))}
          </div>

          {/* Actions */}
          <div className="flex items-center gap-0.5 flex-shrink-0 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity">
            <button
              onClick={handleToggleFavorite}
              disabled={loading}
              className={`star-btn ${highlight.favorite ? 'active' : ''}`}
              title={highlight.favorite ? '取消收藏' : '收藏'}
            >
              <Star size={18} fill={highlight.favorite ? 'currentColor' : 'none'} />
            </button>
            <button
              onClick={handleToggleRead}
              disabled={loading}
              className={`read-btn ${highlight.is_read ? 'active' : ''}`}
              title={highlight.is_read ? '标记未读' : '标记已读'}
            >
              <Check size={18} />
            </button>
            <button
              onClick={e => { e.preventDefault(); e.stopPropagation(); exportHighlightAsMarkdown(highlight); }}
              className="read-btn"
              title="导出 Markdown"
            >
              <Download size={18} />
            </button>
            <button
              onClick={handleDelete}
              disabled={loading}
              className="delete-btn"
              title="删除"
            >
              <Trash2 size={18} />
            </button>
          </div>
        </div>
      </div>
    </Link>
  );
}
