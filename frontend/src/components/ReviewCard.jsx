import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import { Check, X, BookOpen } from 'lucide-react';
import api from '../api';

export default function ReviewCard({ highlight, onComplete }) {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [showAnswer, setShowAnswer] = useState(false);

  const handleReview = async (quality) => {
    setLoading(true);
    try {
      await api.submitReview(highlight.id, quality);
      onComplete?.(highlight.id);
    } catch (err) {
      console.error('Failed to submit review:', err);
    } finally {
      setLoading(false);
    }
  };

  const qualityButtons = [
    { quality: 0, label: '0', desc: 'Blackout', color: 'bg-red-500' },
    { quality: 1, label: '1', desc: 'Wrong', color: 'bg-red-400' },
    { quality: 2, label: '2', desc: 'Hard', color: 'bg-yellow-500' },
    { quality: 3, label: '3', desc: 'Good', color: 'bg-green-400' },
    { quality: 4, label: '4', desc: 'Easy', color: 'bg-green-500' },
    { quality: 5, label: '5', desc: 'Perfect', color: 'bg-green-600' },
  ];

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6">
      {/* Meta */}
      <div className="flex items-center gap-2 text-sm text-gray-500 mb-4">
        {highlight.source && (
          <>
            <BookOpen size={14} />
            <span>{highlight.source}</span>
            {highlight.author && <span>- {highlight.author}</span>}
          </>
        )}
      </div>

      {/* Content */}
      <div className="prose prose-gray max-w-none mb-6">
        <ReactMarkdown>{highlight.text}</ReactMarkdown>
      </div>

      {/* Show answer button */}
      {!showAnswer && (
        <button
          onClick={() => setShowAnswer(true)}
          className="w-full py-3 bg-gray-900 text-white rounded-lg hover:bg-gray-800"
        >
          Show Answer
        </button>
      )}

      {/* Rating buttons */}
      {showAnswer && (
        <div>
          <p className="text-sm text-gray-600 mb-3">How well did you remember?</p>
          <div className="grid grid-cols-6 gap-2">
            {qualityButtons.map((btn) => (
              <button
                key={btn.quality}
                onClick={() => handleReview(btn.quality)}
                disabled={loading}
                className={`${btn.color} text-white py-3 rounded-lg hover:opacity-90 disabled:opacity-50 transition-opacity`}
              >
                <div className="font-bold">{btn.label}</div>
                <div className="text-xs opacity-80">{btn.desc}</div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
