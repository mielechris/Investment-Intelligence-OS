import { createContext, useContext } from 'react';
import { emptyNorthstar, type NorthstarState } from './northstarSession';
export const NorthstarContext = /* @__PURE__ */ createContext<NorthstarState>(emptyNorthstar);
export const useNorthstar = () => useContext(NorthstarContext);
