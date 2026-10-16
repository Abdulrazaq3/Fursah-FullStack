import type { RefObject } from 'react';

const MAX = 2000;
const EXAMPLES = [
  'ورشة في تحليل البيانات بالرياض',
  'فرص في ريادة الأعمال عن بُعد',
  'فرص صحية في أبها أو عن بعد',
];

interface Props {
  inputRef: RefObject<HTMLTextAreaElement>;
  query: string;
  onChange: (q: string) => void;
  onSubmit: () => void;
  loading: boolean;
}

export default function SearchForm({ inputRef, query, onChange, onSubmit, loading }: Props) {
  const len = query.trim().length;
  const disabled = !len || loading;
  return (
    <form
      className="card discovery"
      aria-label="طلب البحث"
      onSubmit={e => { e.preventDefault(); if (!disabled) onSubmit(); }}
    >
      <label htmlFor="fursah-query" className="discovery__label">عمّ تبحث؟</label>
      <textarea
        id="fursah-query"
        ref={inputRef}
        className="textarea"
        rows={3}
        maxLength={MAX}
        value={query}
        placeholder="أخبرنا عن الفرصة التي تبحث عنها…"
        onChange={e => onChange(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && !disabled) onSubmit(); }}
      />
      <div className="discovery__row">
        <div className="examples">
          {EXAMPLES.map(ex => (
            <button type="button" key={ex} className="example" onClick={() => onChange(ex)}>{ex}</button>
          ))}
        </div>
        <span className="counter" dir="ltr">{len}/{MAX}</span>
        <button type="submit" className="btn btn--primary btn--lg" disabled={disabled}>
          {loading ? 'جارٍ البحث…' : 'اكتشف الفرص'}
        </button>
      </div>
    </form>
  );
}
