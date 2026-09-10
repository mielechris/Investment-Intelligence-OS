import { useEffect, useState, type ReactNode } from 'react';
import { emptyNorthstar, observeNorthstar } from './northstarSession';
import { NorthstarContext } from './northstarContext';

export function NorthstarSessionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState(emptyNorthstar);
  useEffect(() => observeNorthstar(setState), []);
  return <NorthstarContext.Provider value={state}>{children}</NorthstarContext.Provider>;
}
