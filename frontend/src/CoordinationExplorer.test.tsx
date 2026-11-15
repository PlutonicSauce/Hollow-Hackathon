import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
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
const score = () => screen.getByRole("status");

describe("coordination counterfactuals", () => {
  it("shows real subset outcomes and timelines when either crew is excluded", async () => {
    const user = userEvent.setup();
    render(view());
    expect(score()).toHaveTextContent("1,100");
    expect(screen.getAllByRole("img", {name: /5 of 6 minutes available/})).toHaveLength(3);
    await user.click(screen.getByRole("switch", {name: "Water tanker crew intervention"}));
    expect(score()).toHaveTextContent("Mobile generator crew only · same score as no actions");
    expect(within(score()).getByText("0", {exact:true})).toBeInTheDocument();
    expect(screen.getAllByRole("img", {name: /0 of 6 minutes available/})).toHaveLength(3);
    await user.click(screen.getByRole("switch", {name: "Mobile generator crew intervention"}));
    expect(score()).toHaveTextContent("No actions");
    await user.click(screen.getByRole("switch", {name: "Water tanker crew intervention"}));
    expect(score()).toHaveTextContent("Water tanker crew only");
    expect(within(score()).getByText("0", {exact:true})).toBeInTheDocument();
    await user.click(screen.getByRole("button", {name: "Both actions 1,100"}));
    expect(score()).toHaveTextContent("1,100");
    expect(screen.getByRole("switch", {name: "Mobile generator crew intervention"})).toBeChecked();
    await user.click(screen.getByText("Minute details for deep shelter: air"));
    expect(screen.getAllByText("Minute 6 (end boundary, not counted): unavailable")).toHaveLength(3);
  });

  it("supports keyboard toggles and blocks exploration of stale results", async () => {
    const user = userEvent.setup();
    const {rerender} = render(view());
    await user.tab();
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
    render(view());
    expect(screen.getByText(/not a globally smallest plan or full recovery/)).toBeInTheDocument();
    await user.click(screen.getByText("What this evidence does and does not show"));
    expect(screen.getByText(/10 certificate replay checks passed/)).toBeInTheDocument();
    expect(screen.getByText(/The builder and verifier share/)).toBeInTheDocument();
    expect(screen.getByText(/Certificate SHA-256/)).toBeInTheDocument();
  });

  it("does not claim coordination for a single-action or idle plan", () => {
    const {unmount} = render(view(single));
    expect(screen.getByText(/No multi-action synergy is claimed/)).toBeInTheDocument();
    expect(score()).toHaveTextContent("1,080");
    unmount();
    render(view(none));
    expect(screen.getByRole("heading", {name: "Service without assigned backup"})).toBeInTheDocument();
    expect(score()).toHaveTextContent("40");
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
  });

  it("does not present a failed replay report as checked", async () => {
    const user = userEvent.setup();
    render(view({...coupled, coordination_verification: {...coupled.coordination_verification, status: "failed"}}));
    await user.click(screen.getByText("What this evidence does and does not show"));
    expect(screen.getByText(/Do not treat this evidence as checked/)).toBeInTheDocument();
    expect(screen.queryByText(/10 certificate replay checks passed/)).not.toBeInTheDocument();
  });
});
