import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { StatCard } from '../Card';

describe('StatCard', () => {
  it('does not render an empty metadata row for trendValue without trend', () => {
    const html = renderToStaticMarkup(
      <StatCard label="Boost" value="55" trendValue="+3%" />,
    );

    expect(html).not.toContain('flex items-center gap-2 mt-1');
    expect(html).not.toContain('+3%');
  });

  it('renders trend metadata when both trend and trendValue are provided', () => {
    const html = renderToStaticMarkup(
      <StatCard label="Boost" value="55" trend="up" trendValue="+3%" />,
    );

    expect(html).toContain('flex items-center gap-2 mt-1');
    expect(html).toContain('↑ +3%');
  });
});
