import type { Company, DataAccess } from './api.ts';
import { ShowcaseDashboard } from './showcase/ShowcaseDashboard.tsx';

export function ResearchHome(props: {
  companies: Company[];
  company: string;
  access?: DataAccess;
}) {
  return <ShowcaseDashboard {...props} />;
}
