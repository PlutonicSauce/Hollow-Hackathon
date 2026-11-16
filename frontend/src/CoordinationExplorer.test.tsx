import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { CoordinationExplorer } from "./CoordinationExplorer";
import type { CoordinationCertificate, Evaluation } from "./types";
import coupled from "./test/fixtures/coordination-coupled-utility.json";
import none from "./test/fixtures/coordination-hand-calculated.json";
import single from "./test/fixtures/coordination-feeder-cascade.json";

// Fixtures are real evaluate_scenario outputs, reduced to the fields this view consumes.
function view(data: typeof coupled | typeof single | typeof none = coupled, stale = false) {
  return <CoordinationExplorer evaluation={data as unknown as Evaluation}
    certificate={data.coordination_certificate as CoordinationCertificate} stale={stale} />;
}
function renderExperiment(element: React.ReactElement) {
  const result = render(element);
  fireEvent.click(screen.getByText("Explore the network and full recovery", {exact:true}));
  fireEvent.click(screen.getByText(/replayed outcomes$/, {exact:false}));
  fireEvent.click(screen.getByRole("button", {name:/^Reset$/}));
  return result;
}
const score = () => screen.getByRole("status");

describe("coordination counterfactuals", () => {
  it("shows real subset outcomes and timelines when either crew is excluded", async () => {
    const user = userEvent.setup();
    renderExperiment(view());
    expect(score()).toHaveTextContent("1,100");
    expect(screen.getByText("Initial state · Includes any backup arriving at minute 0")).toBeInTheDocument();
    expect(screen.getAllByRole("img", {name: /5 of 6 minutes available/})).toHaveLength(2);
    await user.click(screen.getByRole("switch", {name: "Water tanker crew intervention"}));
    expect(score()).toHaveTextContent("Mobile generator crew only · same score as no actions");
    expect(within(score()).getByText("0", {exact:true})).toBeInTheDocument();
    expect(screen.getAllByRole("img", {name: /0 of 6 minutes available/})).toHaveLength(2);
    await user.click(screen.getByRole("switch", {name: "Mobile generator crew intervention"}));
    expect(score()).toHaveTextContent("No actions");
    await user.click(screen.getByRole("switch", {name: "Water tanker crew intervention"}));
    expect(score()).toHaveTextContent("Water tanker crew only");
    expect(within(score()).getByText("0", {exact:true})).toBeInTheDocument();
    await user.click(screen.getByRole("button", {name: "Both actions 1,100"}));
    expect(score()).toHaveTextContent("1,100");
    expect(screen.getByRole("switch", {name: "Mobile generator crew intervention"})).toBeChecked();
    await user.click(screen.getByText("Minute details for deep shelter: air"));
    expect(screen.getAllByText("Minute 6 (end boundary, not counted): unavailable")).toHaveLength(2);
  });

  it("supports keyboard toggles and blocks exploration of stale results", async () => {
    const user = userEvent.setup();
    const {rerender} = renderExperiment(view());
    screen.getByRole("switch", {name: "Mobile generator crew intervention"}).focus();
    expect(screen.getByRole("switch", {name: "Mobile generator crew intervention"})).toHaveFocus();
    await user.keyboard(" ");
    expect(score()).toHaveTextContent("Water tanker crew only");
    rerender(view(coupled, true));
    expect(screen.getByRole("switch", {name: "Mobile generator crew intervention"})).toBeDisabled();
    expect(screen.getByRole("button", {name: "Both actions 1,100"})).toBeDisabled();
    expect(screen.getByText(/evidence belongs to the previous run/)).toBeInTheDocument();
  });

  it("states local minimality and the shared-formula verification boundary", async () => {
    const user = userEvent.setup();
    renderExperiment(view());
    expect(screen.getByText(/not a globally smallest plan or full recovery/)).toBeInTheDocument();
    await user.click(screen.getByText("What this evidence does and does not show"));
    expect(screen.getByText(/10 certificate replay checks passed/)).toBeInTheDocument();
    expect(screen.getByText(/The builder and verifier share/)).toBeInTheDocument();
    expect(screen.getByText(/Certificate SHA-256/)).toBeInTheDocument();
  });

  it("does not claim coordination for a single-action or idle plan", () => {
    const {unmount} = renderExperiment(view(single));
    expect(screen.getByText(/No multi-action synergy is claimed/)).toBeInTheDocument();
    expect(score()).toHaveTextContent("1,080");
    unmount();
    renderExperiment(view(none));
    expect(screen.getByRole("heading", {name: "Service without assigned backup"})).toBeInTheDocument();
    expect(score()).toHaveTextContent("40");
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
  });

  it("does not present a failed replay report as checked", async () => {
    const user = userEvent.setup();
    renderExperiment(view({...coupled, coordination_verification: {...coupled.coordination_verification, status: "failed"}}));
    await user.click(screen.getByText("What this evidence does and does not show"));
    expect(screen.getByText(/Do not treat this evidence as checked/)).toBeInTheDocument();
    expect(screen.queryByText(/10 certificate replay checks passed/)).not.toBeInTheDocument();
  });
  it("keeps graph, selected minute and score on one recorded subset, including comparisons", async () => {
    const user = userEvent.setup();
    renderExperiment(view());
    fireEvent.change(screen.getByRole("slider", {name: "Counterfactual minute"}), {target:{value:"1"}});
    const pump = () => screen.getByRole("button", {name: /Shared water pump/});
    expect(pump()).toHaveTextContent("Service available");
    await user.click(screen.getByRole("switch", {name:"Water tanker crew intervention"}));
    expect(pump()).toHaveTextContent("Service unavailable");
    expect(within(score()).getByText("0", {exact:true})).toBeInTheDocument();
    expect(screen.getByRole("slider", {name:"Counterfactual minute"})).toHaveValue("1");
    await user.click(screen.getByRole("button", {name:"Both actions 1,100"}));
    expect(pump()).toHaveTextContent("Service available");
    await user.click(screen.getByText("Compare other responses", {exact:true}));
    await user.click(screen.getByRole("button", {name:"Greedy response 720"}));
    expect(score()).toHaveTextContent("720");
    expect(pump()).toHaveTextContent("Service unavailable");
    expect(screen.getByText("Exploring a counterfactual")).toBeInTheDocument();
    await user.click(screen.getByRole("button", {name:"Static priority 720"}));
    expect(score()).toHaveTextContent("720");
    await user.click(screen.getByRole("button", {name:"Both actions 1,100"}));
    expect(pump()).toHaveTextContent("Service available");
    expect(screen.getByText("Recommended response", {exact:true})).toBeInTheDocument();
  });

  it("replays recorded boundaries and stops playback when inputs become stale", () => {
    vi.useFakeTimers();
    try {
      const {rerender} = renderExperiment(view());
      fireEvent.click(screen.getByRole("button", {name:"Watch recovery"}));
      act(() => vi.advanceTimersByTime(850));
      expect(screen.getByRole("slider", {name:"Counterfactual minute"})).toHaveValue("1");
      expect(screen.getByRole("button", {name:/Shared water pump/})).toHaveTextContent("Service available");
      rerender(view(coupled,true));
      act(() => vi.advanceTimersByTime(1700));
      expect(screen.getByRole("slider", {name:"Counterfactual minute"})).toHaveValue("1");
      expect(screen.getByRole("button", {name:"Watch recovery"})).toBeDisabled();
    } finally {vi.useRealTimers();}
  });

  it("leads with community consequences and defers numerical evidence", async () => {
    const user = userEvent.setup();
    render(view());
    const services = screen.getByLabelText("Recorded community outcomes");
    expect(services).toHaveTextContent("VentilationAvailable");
    expect(screen.getByText("Explore the network and full recovery", {exact:true}).closest("details")).not.toHaveAttribute("open");
    await user.click(screen.getByRole("switch", {name:"Water tanker crew intervention"}));
    expect(services).toHaveTextContent("VentilationUnavailable");
    expect(screen.getByLabelText("Required pump inputs")).toHaveTextContent("WaterRequired input missing");
    await user.click(screen.getByRole("switch", {name:"Mobile generator crew intervention"}));
    expect(screen.getAllByText("Required input missing")).toHaveLength(2);
    await user.click(screen.getByRole("switch", {name:"Water tanker crew intervention"}));
    expect(services).toHaveTextContent("WaterUnavailable");
    await user.click(screen.getByRole("switch", {name:"Mobile generator crew intervention"}));
    expect(services).toHaveTextContent("WaterAvailable");
  });

});
