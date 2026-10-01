import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";

import { App } from "../App";
import { ToastProvider } from "../components/ui";

export function renderApp(entry: string) {
  return render(
    <ToastProvider>
      <MemoryRouter initialEntries={[entry]}>
        <App />
      </MemoryRouter>
    </ToastProvider>,
  );
}

export function renderPage(element: ReactElement, entry = "/") {
  return render(
    <ToastProvider>
      <MemoryRouter initialEntries={[entry]}>{element}</MemoryRouter>
    </ToastProvider>,
  );
}
