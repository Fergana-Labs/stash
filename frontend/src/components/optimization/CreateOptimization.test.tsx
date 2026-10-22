import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import CreateOptimization from "./CreateOptimization";

const api = vi.hoisted(() => ({ models: vi.fn(), create: vi.fn(), push: vi.fn(), evals: vi.fn(), evalDetail: vi.fn() }));
vi.mock("@/lib/api", () => ({ rmListRewardModels: api.models }));
vi.mock("@/lib/optimization-api", () => ({ createOptimization: api.create }));
vi.mock("@/lib/intuition-api", () => ({ imList: api.evals, imGet: api.evalDetail }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: api.push }) }));

beforeEach(() => {
  vi.clearAllMocks();
  api.models.mockResolvedValue([{ id:"truck",name:"Truck reward",status:"succeeded",metrics:{action_scoring_version:1} },{ id:"other",name:"Other reward",status:"succeeded",metrics:{action_scoring_version:1} },{id:"unready",name:"Still training",status:"running",metrics:{} }]);
  api.create.mockResolvedValue({ id:"optimization" });
  api.evals.mockResolvedValue({ models: [{ id:"reply-eval", name:"Reply quality", active_version_id:"v2" }, { id:"unsaved", name:"Unsaved eval", active_version_id:null }] });
  api.evalDetail.mockResolvedValue({ model: { output_type:"choice" }, active: { labels: [{ id:"send" }, { id:"rewrite" }] } });
});

it("starts against the selected reward model without business measurements or extra required setup",async () => {
  render(<CreateOptimization initialAgent="heavi-chat" initialModelId="truck" />);
  await waitFor(() => expect(screen.getByRole("button",{name:"Start optimization"})).toBeEnabled());
  expect(screen.queryByText("What business result matters?")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Business metric")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Agent")).not.toBeInTheDocument();
  expect(screen.getByRole("combobox",{name:"Reward model or eval to optimize against"})).toHaveValue("rm:truck");
  fireEvent.click(screen.getByRole("button",{name:"Start optimization"}));
  await waitFor(() => expect(api.create).toHaveBeenCalledWith({name:"heavi-chat · Truck reward",reward_model_id:"truck",agent:"heavi-chat",scope:"default",initial_prompt:"",runs_per_arm:20,max_rounds:10}));
  expect(api.push).toHaveBeenCalledWith("/reward-models/optimization/optimization");
});

it("uses a newly selected model and preserves optional prompt and workload settings",async () => {
  render(<CreateOptimization initialAgent="heavi-chat" initialModelId="truck" />);
  await waitFor(() => expect(screen.getByRole("button",{name:"Start optimization"})).toBeEnabled());
  fireEvent.change(screen.getByRole("combobox",{name:"Reward model or eval to optimize against"}),{target:{value:"rm:other"}});
  fireEvent.click(screen.getByText("Optional settings"));
  fireEvent.change(screen.getByLabelText("Current prompt"),{target:{value:"Verify fitment"}});
  fireEvent.change(screen.getByLabelText("Workload",{exact:false}),{target:{value:"parts/support"}});
  fireEvent.click(screen.getByRole("button",{name:"Start optimization"}));
  await waitFor(() => expect(api.create).toHaveBeenCalledWith(expect.objectContaining({reward_model_id:"other",initial_prompt:"Verify fitment",scope:"parts/support"})));
  expect(api.create.mock.calls[0][0]).not.toHaveProperty("metric");
});

it("requires choosing a usable reward model if the previous selection is unavailable",async () => {
  render(<CreateOptimization initialAgent="heavi-chat" initialModelId="unready" />);
  await waitFor(() => expect(api.models).toHaveBeenCalled());
  expect(screen.getByRole("button",{name:"Start optimization"})).toBeDisabled();
  expect(screen.queryByRole("option",{name:"Still training"})).not.toBeInTheDocument();
  expect(api.create).not.toHaveBeenCalled();
});

it("scores runs with a saved eval and the decision that counts as success",async () => {
  render(<CreateOptimization initialAgent="support" />);
  const picker = await screen.findByRole("combobox",{name:"Reward model or eval to optimize against"});
  await waitFor(() => expect(screen.getByRole("option",{name:"Reply quality"})).toBeInTheDocument());
  expect(screen.queryByRole("option",{name:"Unsaved eval"})).not.toBeInTheDocument();
  fireEvent.change(picker,{target:{value:"eval:reply-eval"}});
  const success = await screen.findByRole("combobox",{name:"Decision that counts as success"});
  await waitFor(() => expect(success).toHaveValue("send"));
  fireEvent.change(success,{target:{value:"rewrite"}});
  expect(screen.getByText(/“Reply quality” eval \(its saved version, pinned\) scores each run by how likely it decides “rewrite”/)).toBeVisible();
  fireEvent.click(screen.getByRole("button",{name:"Start optimization"}));
  await waitFor(() => expect(api.create).toHaveBeenCalledWith(expect.objectContaining({ eval_id:"reply-eval", target_label:"rewrite", name:"support · Reply quality" })));
  expect(api.create.mock.calls[0][0]).not.toHaveProperty("reward_model_id");
});
