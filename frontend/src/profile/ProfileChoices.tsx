import { useEffect, useId, useRef, useState } from 'react';

import { INTERESTS } from './choices';

/** Selection only: typed text filters approved options and is never a saved value. */
export function Choice({ label, value, options, onChange, empty = 'غير معروف', searchable = false, missing = false }: {
  label: string; value: string; options: string[]; onChange: (value: string) => void; empty?: string; searchable?: boolean; missing?: boolean;
}) {
  if (searchable) return <SearchChoice label={label} value={value} options={options} onChange={onChange} empty={empty} missing={missing} />;
  return <label className="field">{label}{missing && <span className="field__required"> — مطلوب لاستكمال البحث</span>}
    <select aria-invalid={missing || undefined} className={`input${missing ? ' is-missing' : ''}`} value={value} onChange={e => onChange(e.target.value)}>
      <option value="">{empty}</option>
      {options.map(x => <option key={x} value={x}>{x}</option>)}
    </select>
  </label>;
}

/** Search and selection share one accessible combobox. */
function SearchChoice({ label, value, options, onChange, empty, missing }: {
  label: string; value: string; options: string[]; onChange: (value: string) => void; empty: string; missing: boolean;
}) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [search, setSearch] = useState(value);
  useEffect(() => setSearch(value), [value]);
  const matches = options.filter(option => option.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()));
  const items = [
    ...matches.map(text => ({ value: text, text })),
    { value: '', text: `مسح الاختيار — ${empty}` },
  ];
  function choose(next: string) { onChange(next); setSearch(next); setOpen(false); setActive(-1); }
  return <div className="field search-choice">
    <label htmlFor={id}>{label}{missing && <span className="field__required"> — مطلوب لاستكمال البحث</span>}</label>
    <input id={id} aria-invalid={missing || undefined} className={`input${missing ? ' is-missing' : ''}`} role="combobox" autoComplete="off" maxLength={label === 'التخصص' ? 200 : 120}
      aria-autocomplete="list" aria-expanded={open} aria-controls={`${id}-options`}
      aria-activedescendant={open && active >= 0 ? `${id}-option-${active}` : undefined}
      aria-describedby={label === 'التخصص' ? `${id}-hint` : undefined} placeholder={`ابحث واختر ${label}`} value={search}
      onFocus={() => { setOpen(true); setActive(-1); }}
      onBlur={() => { setOpen(false); setActive(-1); setSearch(value); }}
      onChange={e => { setSearch(e.target.value); setOpen(true); setActive(-1); }}
      onKeyDown={e => {
        if (e.key === 'Escape' && open) { e.preventDefault(); e.stopPropagation(); setOpen(false); setActive(-1); }
        else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
          e.preventDefault(); setOpen(true);
          const next = e.key === 'ArrowDown' ? (active + 1) % items.length : (active <= 0 ? items.length - 1 : active - 1);
          setActive(next);
          requestAnimationFrame(() => document.getElementById(`${id}-option-${next}`)?.scrollIntoView({ block: 'nearest' }));
        } else if (e.key === 'Enter' && open) {
          e.preventDefault();
          if (active >= 0) choose(items[active].value);
          else if (matches.length) choose(matches[0]);
        }
      }} />
    {open && <ul id={`${id}-options`} className="search-choice__options" role="listbox" aria-label={`خيارات ${label}`}>
      {items.map((item, i) => <li key={item.value} id={`${id}-option-${i}`} role="option"
        aria-selected={item.value === value} className={i === active ? 'is-active' : ''}
        onMouseDown={e => e.preventDefault()} onClick={() => choose(item.value)}>{item.text}</li>)}
    </ul>}
    {label === 'التخصص' && <span id={`${id}-hint`} className="field__hint">ابحث ثم اختر من القائمة فقط. الكتابة وحدها لا تغيّر الاختيار المحفوظ. الحقل الفارغ يعني غير معروف.</span>}
  </div>;
}

export function InterestChoices(props: { missing?: boolean; values: string[]; onChange: (values: string[]) => void }) {
  return <MultiChoice {...props} label="الاهتمامات" options={INTERESTS} />;
}

export function MultiChoice({ values, onChange, label, options, missing = false }: { missing?: boolean; values: string[]; onChange: (values: string[]) => void; label: string; options: string[] }) {
  const id = useId();
  const input = useRef<HTMLInputElement>(null);
  const [search, setSearch] = useState('');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const term = search.trim();
  const same = (a: string, b: string) => a.toLocaleLowerCase() === b.toLocaleLowerCase();
  const available = options.filter(x => !values.some(v => same(v, x)) && x.toLocaleLowerCase().includes(term.toLocaleLowerCase()));
  const items = available.map(value => ({ value, text: value }));
  function add(value: string) {
    if (options.includes(value) && !values.some(v => same(v, value))) onChange([...values, value]);
    setSearch(''); setActive(-1); setOpen(true); input.current?.focus();
  }
  return <div className="field field--full">
    <label htmlFor={id}>{label}{missing && <span className="field__required"> — مطلوب لاستكمال البحث</span>}</label>
    <div className="interest-picker" onBlur={e => {
      if (!e.currentTarget.contains(e.relatedTarget as Node | null)) { setOpen(false); setActive(-1); }
    }}>
      <div className={`interest-picker__control${missing ? ' is-missing' : ''}`} onClick={() => input.current?.focus()}>
        {values.map(value => <span className="interest-picker__tag" key={value}>
          <span>{value}</span>
          <button type="button" aria-label={`إزالة ${value}`} onClick={e => {
            e.stopPropagation(); onChange(values.filter(v => v !== value)); input.current?.focus();
          }}>×</button>
        </span>)}
        <input aria-invalid={missing || undefined} ref={input} id={id} role="combobox" autoComplete="off" maxLength={120}
          aria-autocomplete="list" aria-expanded={open} aria-controls={`${id}-options`}
          aria-activedescendant={open && active >= 0 ? `${id}-option-${active}` : undefined}
          aria-describedby={`${id}-hint`} placeholder={`ابحث واختر ${label}…`}
          value={search} onFocus={() => setOpen(true)}
          onChange={e => { setSearch(e.target.value); setActive(-1); setOpen(true); }}
          onKeyDown={e => {
            if (e.key === 'Escape' && open) { e.preventDefault(); e.stopPropagation(); setOpen(false); setActive(-1); }
            else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
              e.preventDefault(); setOpen(true);
              if (!items.length) return;
              const next = e.key === 'ArrowDown' ? (active + 1) % items.length : (active <= 0 ? items.length - 1 : active - 1);
              setActive(next);
              requestAnimationFrame(() => document.getElementById(`${id}-option-${next}`)?.scrollIntoView({ block: 'nearest' }));
            } else if (e.key === 'Enter') {
              e.preventDefault();
              if (open && items.length && (active >= 0 || term)) add(items[active >= 0 ? active : 0].value);
            }
          }} />
      </div>
      {open && <ul id={`${id}-options`} role="listbox" aria-label={`خيارات ${label}`} className="search-choice__options interest-picker__options">
        {items.map((item, i) => <li key={item.value} id={`${id}-option-${i}`} role="option" aria-selected={false}
          className={i === active ? 'is-active' : ''} onMouseDown={e => e.preventDefault()} onClick={() => add(item.value)}>{item.text}</li>)}
        {!items.length && <li role="presentation" className="muted">لا توجد خيارات إضافية مطابقة.</li>}
      </ul>}
    </div>
    <span id={`${id}-hint`} className="field__hint">اختر قيمة أو أكثر من القائمة فقط، واحذف بالضغط على ×. لا اختيار يعني غير معروف أو بلا تفضيل.</span>
  </div>;
}
