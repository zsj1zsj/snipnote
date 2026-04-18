import { useState, useEffect } from 'react';
import { Tag, Edit2, Trash2, Info } from 'lucide-react';
import api from '../api';

export default function TagManager() {
  const [tags, setTags] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editingTag, setEditingTag] = useState(null);
  const [newName, setNewName] = useState('');

  useEffect(() => {
    loadTags();
  }, []);

  const loadTags = async () => {
    setLoading(true);
    try {
      const data = await api.getTags();
      setTags(data);
    } catch (err) {
      console.error('Failed to load tags:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleRename = async (oldName) => {
    if (!newName.trim() || newName === oldName) {
      setEditingTag(null);
      return;
    }
    try {
      await api.renameTag(oldName, newName);
      loadTags();
    } catch (err) {
      console.error('Failed to rename tag:', err);
    }
    setEditingTag(null);
  };

  const handleDelete = async (name) => {
    if (!confirm(`确定要删除标签 "${name}" 吗？这将从所有摘录中移除该标签。`)) return;
    try {
      await api.deleteTag(name);
      loadTags();
    } catch (err) {
      console.error('Failed to delete tag:', err);
    }
  };

  return (
    <div className="page-container">
      <h1 className="page-title flex items-center gap-3">
        <Tag size={28} className="text-gray-600" />
        标签管理
      </h1>

      {/* Hint */}
      <div className="card p-4 mb-6 flex items-start gap-3 bg-blue-50 border-blue-100">
        <Info size={20} className="text-blue-500 flex-shrink-0 mt-0.5" />
        <div className="text-sm text-blue-700">
          标签会在你添加摘录时自动创建。在摘录详情页可以为摘录添加或修改标签。
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="spinner w-8 h-8"></div>
        </div>
      ) : tags.length === 0 ? (
        <div className="empty-state">
          <Tag size={48} className="empty-state-icon mx-auto" />
          <div className="empty-state-title">还没有标签</div>
          <div className="empty-state-description">为摘录添加标签后，它们会显示在这里</div>
        </div>
      ) : (
        <div className="card overflow-hidden divide-y divide-gray-100">
          {tags.map((tag) => (
            <div key={tag.name} className="p-4 flex items-center justify-between gap-3">
              <div className="flex-1 min-w-0">
                {editingTag === tag.name ? (
                  <input
                    type="text"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    onBlur={() => handleRename(tag.name)}
                    onKeyDown={(e) => e.key === 'Enter' && handleRename(tag.name)}
                    className="input py-1.5 px-2 text-sm w-full"
                    autoFocus
                  />
                ) : (
                  <span className="flex items-center gap-2 font-medium">
                    <Tag size={16} className="text-gray-400 flex-shrink-0" />
                    <span className="truncate">{tag.name}</span>
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                <span className="tag tag-gray">{tag.count}</span>
                <button
                  onClick={() => {
                    setEditingTag(tag.name);
                    setNewName(tag.name);
                  }}
                  className="icon-btn text-gray-400 hover:text-gray-600 p-2.5"
                >
                  <Edit2 size={16} />
                </button>
                <button
                  onClick={() => handleDelete(tag.name)}
                  className="icon-btn text-gray-400 hover:text-red-500 p-2.5"
                >
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
