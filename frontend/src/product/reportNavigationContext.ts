import { createContext, useContext } from 'react';
export type EditorState = { dirty: boolean; pending: boolean };
export const ReportNavigationContext = createContext({ setEditorState: (_state: EditorState) => {}, requestLeave: (action: () => void) => action() });
export const useReportNavigation = () => useContext(ReportNavigationContext);
