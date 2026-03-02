import { Link } from 'react-router-dom';
import { Star, Check, Trash2, BookOpen } from 'lucide-react';
import { useState } from 'react';
import api from '../api';

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

  // Display summary if available, otherwise first 300 chars of text
  const displayContent = highlight.summary || (highlight.text ? highlight.text.slice(0, 300) + (highlight.text.length > 300 ? '...' : '') : '');

  return (
    <Link
      to={`/highlight/${highlight.id}`}
      className="highlight-card block group"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          {/* Source and meta */}
          <div className="flex items-center gap-2 text-sm text-gray-400 mb-3">
            {highlight.source ? (
              <>
                <BookOpen size={14} className="flex-shrink-0" />
                <span className="truncate font-medium">{highlight.source}</span>
                {highlight.author && (
                  <span className="text-gray-400 truncate">- {highlight.author}</span>
                )}
              </>
            ) : null}
            {highlight.next_review && highlight.next_review <= new Date().toISOString().split('T')[0] && (
              <span className="tag tag-red text-xs ml-auto">
                待复习
              </span>
            )}
            {highlight.is_read === 1 && (
              <span className="tag tag-green text-xs">
                已读
              </span>
            )}
          </div>

          {/* Text content - summary or first 300 chars */}
          <div className="text-content mb-4">
            {displayContent}
          </div>

          {/* Tags */}
          {tags.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {tags.map((tag) => (
                <span key={tag} className="tag tag-gray">
                  #{tag}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex flex-col gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
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
            onClick={handleDelete}
            disabled={loading}
            className="delete-btn"
            title="删除"
          >
            <Trash2 size={18} />
          </button>
        </div>
      </div>
    </Link>
  );
}
