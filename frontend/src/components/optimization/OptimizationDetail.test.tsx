import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import OptimizationDetail from "./OptimizationDetail";

const api = vi.hoisted(() => ({ detail: vi.fn() }));
vi.mock("@/lib/optimization-api", () => ({getOptimization:api.detail}));
vi.mock("next/navigation", () => ({usePathname:()=>"/reward-models/optimization/test"}));

it("renders reward-only comparisons and connection instructions without requiring external outcomes",async () => {
  const arm={assigned:5,completed:5,reward:{n:5,mean:0.2,low:0.1,high:0.3},business:{n:0,mean:null,low:null,high:null}};
  api.detail.mockResolvedValue({id:"test",name:"Parts optimization",agent:"heavi-chat",scope:"default",status:"active",metric:null,active_revision_id:"r1",runs_per_arm:5,max_rounds:1,error:null,reward_model:{id:"model",name:"Truck reward",status:"succeeded"},revisions:[{id:"r1",version:1,content:"",rationale:"Original",created_at:"2026-10-12"}],rounds:[{id:"round",number:1,baseline_id:"r1",candidate_id:"r2",status:"collecting",report:{arms:{baseline:arm,candidate:arm},reason:"Waiting for reward scores"}}],runs:[{id:"run",revision_id:"r1",work_key:"Task",agent_version:"agent-1",arm:"baseline",status:"assigned",reward:null,outcome:null,assigned_at:"2026-10-12",trace_id:null}],trends:[],events:[]});
  render(<OptimizationDetail id="test" />);
  expect(await screen.findByRole("heading",{name:"Parts optimization"})).toBeVisible();
  expect(screen.getByText(/Truck reward; higher reward is the optimization objective/)).toBeInTheDocument();
  expect(screen.getByRole("columnheader",{name:"Mean reward"})).toBeVisible();
  expect(screen.queryByText("Business measured")).not.toBeInTheDocument();
  expect(screen.queryByText("Record outcome")).not.toBeInTheDocument();
  expect(screen.queryByText(/stash_optimization_record_outcome/)).not.toBeInTheDocument();
});

it("describes an eval-scored program by its pinned eval and success decision",async () => {
  const arm={assigned:5,completed:5,reward:{n:5,mean:0.2,low:0.1,high:0.3},business:{n:0,mean:null,low:null,high:null}};
  api.detail.mockResolvedValue({id:"test",name:"Parts optimization",agent:"heavi-chat",scope:"default",status:"active",metric:null,active_revision_id:"r1",runs_per_arm:5,max_rounds:1,error:null,reward_model:null,eval:{id:"e",name:"Reply quality",output_type:"choice",version:3,target_label:"send"},revisions:[{id:"r1",version:1,content:"",rationale:"Original",created_at:"2026-10-12"}],rounds:[{id:"round",number:1,baseline_id:"r1",candidate_id:"r2",status:"collecting",report:{arms:{baseline:arm,candidate:arm},reason:"Waiting for reward scores"}}],runs:[{id:"run",revision_id:"r1",work_key:"Task",agent_version:"agent-1",arm:"baseline",status:"assigned",reward:null,outcome:null,assigned_at:"2026-10-12",trace_id:null}],trends:[],events:[]});
  render(<OptimizationDetail id="test" />);
  expect(await screen.findByRole("heading",{name:"Parts optimization"})).toBeVisible();
  expect(screen.getByText(/the “Reply quality” eval \(v3\); higher reward is the optimization objective/)).toBeInTheDocument();
  expect(screen.getByText(/probability the eval decides “send”/)).toBeInTheDocument();
});
