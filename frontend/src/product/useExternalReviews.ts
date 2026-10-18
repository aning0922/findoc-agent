import { useEffect, useMemo, useState } from 'react';
import type { OperatingReviewTarget, ReviewMatch } from './externalReview.ts';
import { matchOperatingReviews } from './externalReview.ts';

export function useReview<T>(owner: T, match: (owner: T) => Promise<ReviewMatch>): ReviewMatch | null {
  const [reading, setReading] = useState<{ owner: T; value: ReviewMatch } | null>(null);
  useEffect(() => {
    let active = true;
    void match(owner).then(value => { if (active) setReading({ owner, value }); });
    return () => { active = false; };
  }, [owner, match]);
  return reading?.owner === owner ? reading.value : null;
}
export function useOperatingReviews(target: OperatingReviewTarget | null): ReviewMatch | null {
  // The target is derived from the currently displayed immutable Task/report.
  const key = JSON.stringify(target);
  const stable = useMemo(() => JSON.parse(key) as OperatingReviewTarget | null, [key]);
  return useReview(stable, matchOperatingReviews);
}
