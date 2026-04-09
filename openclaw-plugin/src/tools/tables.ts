import type { OpenClawPluginApi } from "openclaw/plugin-sdk/plugin-entry";
import { textResult } from "../utils/tool-result.js";
/**
 * Table tools — list, create, get schema, read rows, insert, update, delete.
 */

import { Type } from "@sinclair/typebox";
import type { OctopusClient } from "../octopus-client.js";

export function registerTableTools(
  api: OpenClawPluginApi,
  client: OctopusClient,
) {
  api.registerTool({
    name: "octopus_list_tables",
    description: "List tables in a Octopus workspace",
    label: "List tables in a Octopus workspace",
    parameters: Type.Object({
      workspace_id: Type.String({ description: "Workspace UUID" }),
    }),
    async execute(_id: string, params: { workspace_id: string }) {
      const result = await client.listTables(params.workspace_id);
      return textResult(JSON.stringify(result, null, 2));
    },
  });

  api.registerTool({
    name: "octopus_create_table",
    description:
      "Create a new table in a Octopus workspace. Columns: [{name, type}]. " +
      "Types: text, number, boolean, date, datetime, url, email, select, multiselect, json. " +
      "For select/multiselect, include an 'options' array.",
    label: "Create a table in a Octopus workspace",
    parameters: Type.Object({
      workspace_id: Type.String({ description: "Workspace UUID" }),
      name: Type.String({ description: "Table name" }),
      description: Type.Optional(Type.String({ description: "Table description" })),
      columns: Type.Optional(
        Type.String({ description: 'JSON array of {name, type, options?} objects, e.g. [{"name":"Status","type":"select","options":["todo","done"]}]' }),
      ),
    }),
    async execute(_id: string, params: { workspace_id: string; name: string; description?: string; columns?: string }) {
      const cols = params.columns ? JSON.parse(params.columns) : [];
      const result = await client.createTable(
        params.workspace_id,
        params.name,
        params.description ?? "",
        cols,
      );
      return textResult(JSON.stringify(result, null, 2));
    },
  });

  api.registerTool({
    name: "octopus_get_table_schema",
    description: "Get a table's column schema and metadata",
    label: "Get table schema from Octopus",
    parameters: Type.Object({
      workspace_id: Type.String({ description: "Workspace UUID" }),
      table_id: Type.String({ description: "Table UUID" }),
    }),
    async execute(_id: string, params: { workspace_id: string; table_id: string }) {
      const result = await client.getTable(params.workspace_id, params.table_id);
      return textResult(JSON.stringify(result, null, 2));
    },
  });

  api.registerTool({
    name: "octopus_read_table_rows",
    description:
      "Read rows from a table with optional filtering and sorting. " +
      'filters is JSON: [{"column_id":"col_x","op":"eq","value":"foo"}]. ' +
      "Ops: eq, neq, gt, gte, lt, lte, contains, is_empty, is_not_empty.",
    label: "Read rows from a Octopus table",
    parameters: Type.Object({
      workspace_id: Type.String({ description: "Workspace UUID" }),
      table_id: Type.String({ description: "Table UUID" }),
      limit: Type.Optional(Type.Number({ description: "Max rows to return (default 50)" })),
      offset: Type.Optional(Type.Number({ description: "Skip first N rows (default 0)" })),
      sort_by: Type.Optional(Type.String({ description: "Column ID to sort by" })),
      sort_order: Type.Optional(Type.String({ description: "asc or desc (default asc)" })),
      filters: Type.Optional(Type.String({ description: "JSON array of filter objects" })),
    }),
    async execute(
      _id: string,
      params: {
        workspace_id: string;
        table_id: string;
        limit?: number;
        offset?: number;
        sort_by?: string;
        sort_order?: string;
        filters?: string;
      },
    ) {
      const result = await client.listTableRows(
        params.workspace_id,
        params.table_id,
        params.limit ?? 50,
        params.offset ?? 0,
        params.sort_by ?? "",
        params.sort_order ?? "asc",
        params.filters ?? "",
      );
      return textResult(JSON.stringify(result, null, 2));
    },
  });

  api.registerTool({
    name: "octopus_insert_table_row",
    description:
      "Insert a row into a table. data is a JSON object mapping column names to values. " +
      'Example: {"Name": "Alice", "Status": "active"}',
    label: "Insert a row into a Octopus table",
    parameters: Type.Object({
      workspace_id: Type.String({ description: "Workspace UUID" }),
      table_id: Type.String({ description: "Table UUID" }),
      data: Type.String({ description: "JSON object of column_name: value pairs" }),
    }),
    async execute(_id: string, params: { workspace_id: string; table_id: string; data: string }) {
      const rowData = JSON.parse(params.data);
      // Resolve column names to IDs
      const table = (await client.getTable(params.workspace_id, params.table_id)) as any;
      const cols = table.columns ?? [];
      const nameToId: Record<string, string> = {};
      const idSet = new Set<string>();
      for (const col of cols) {
        nameToId[col.name] = col.id;
        idSet.add(col.id);
      }
      const resolved: Record<string, unknown> = {};
      for (const [k, v] of Object.entries(rowData)) {
        if (idSet.has(k)) resolved[k] = v;
        else if (nameToId[k]) resolved[nameToId[k]] = v;
      }
      const result = await client.insertTableRow(params.workspace_id, params.table_id, resolved);
      return textResult(JSON.stringify(result, null, 2));
    },
  });

  api.registerTool({
    name: "octopus_insert_table_rows_batch",
    description:
      "Batch insert rows into a table. rows is a JSON array of data objects. " +
      'Example: [{"Name": "Alice"}, {"Name": "Bob"}]',
    label: "Batch insert rows into a Octopus table",
    parameters: Type.Object({
      workspace_id: Type.String({ description: "Workspace UUID" }),
      table_id: Type.String({ description: "Table UUID" }),
      rows: Type.String({ description: "JSON array of {column_name: value} objects" }),
    }),
    async execute(_id: string, params: { workspace_id: string; table_id: string; rows: string }) {
      const rowsData = JSON.parse(params.rows) as Record<string, unknown>[];
      // Resolve column names to IDs
      const table = (await client.getTable(params.workspace_id, params.table_id)) as any;
      const cols = table.columns ?? [];
      const nameToId: Record<string, string> = {};
      const idSet = new Set<string>();
      for (const col of cols) {
        nameToId[col.name] = col.id;
        idSet.add(col.id);
      }
      const resolvedRows = rowsData.map((rd) => {
        const resolved: Record<string, unknown> = {};
        for (const [k, v] of Object.entries(rd)) {
          if (idSet.has(k)) resolved[k] = v;
          else if (nameToId[k]) resolved[nameToId[k]] = v;
        }
        return { data: resolved };
      });
      const result = await client.insertTableRowsBatch(params.workspace_id, params.table_id, resolvedRows);
      return textResult(JSON.stringify(result, null, 2));
    },
  });

  api.registerTool({
    name: "octopus_update_table_row",
    description:
      "Update a row in a table (partial merge). data is a JSON object with column names as keys. " +
      'Example: {"Status": "done"}',
    label: "Update a row in a Octopus table",
    parameters: Type.Object({
      workspace_id: Type.String({ description: "Workspace UUID" }),
      table_id: Type.String({ description: "Table UUID" }),
      row_id: Type.String({ description: "Row UUID" }),
      data: Type.String({ description: "JSON object of column_name: value pairs to update" }),
    }),
    async execute(_id: string, params: { workspace_id: string; table_id: string; row_id: string; data: string }) {
      const rowData = JSON.parse(params.data);
      // Resolve column names to IDs
      const table = (await client.getTable(params.workspace_id, params.table_id)) as any;
      const cols = table.columns ?? [];
      const nameToId: Record<string, string> = {};
      const idSet = new Set<string>();
      for (const col of cols) {
        nameToId[col.name] = col.id;
        idSet.add(col.id);
      }
      const resolved: Record<string, unknown> = {};
      for (const [k, v] of Object.entries(rowData)) {
        if (idSet.has(k)) resolved[k] = v;
        else if (nameToId[k]) resolved[nameToId[k]] = v;
      }
      const result = await client.updateTableRow(params.workspace_id, params.table_id, params.row_id, resolved);
      return textResult(JSON.stringify(result, null, 2));
    },
  });

  api.registerTool({
    name: "octopus_delete_table_row",
    description: "Delete a row from a Octopus table",
    label: "Delete a row from a Octopus table",
    parameters: Type.Object({
      workspace_id: Type.String({ description: "Workspace UUID" }),
      table_id: Type.String({ description: "Table UUID" }),
      row_id: Type.String({ description: "Row UUID" }),
    }),
    async execute(_id: string, params: { workspace_id: string; table_id: string; row_id: string }) {
      await client.deleteTableRow(params.workspace_id, params.table_id, params.row_id);
      return textResult("Row deleted.");
    },
  });

  api.registerTool({
    name: "octopus_add_table_column",
    description:
      "Add a column to a Octopus table. For select/multiselect, provide options as comma-separated string.",
    label: "Add a column to a Octopus table",
    parameters: Type.Object({
      workspace_id: Type.String({ description: "Workspace UUID" }),
      table_id: Type.String({ description: "Table UUID" }),
      name: Type.String({ description: "Column name" }),
      column_type: Type.Optional(Type.String({ description: "Column type (default: text)" })),
      options: Type.Optional(Type.String({ description: "Comma-separated options for select/multiselect" })),
    }),
    async execute(
      _id: string,
      params: { workspace_id: string; table_id: string; name: string; column_type?: string; options?: string },
    ) {
      const opts = params.options
        ? params.options.split(",").map((o) => o.trim()).filter(Boolean)
        : [];
      const result = await client.addTableColumn(
        params.workspace_id,
        params.table_id,
        params.name,
        params.column_type ?? "text",
        opts,
      );
      return textResult(JSON.stringify(result, null, 2));
    },
  });

  api.registerTool({
    name: "octopus_delete_table_column",
    description: "Delete a column from a Octopus table",
    label: "Delete a column from a Octopus table",
    parameters: Type.Object({
      workspace_id: Type.String({ description: "Workspace UUID" }),
      table_id: Type.String({ description: "Table UUID" }),
      column_id: Type.String({ description: "Column ID (col_xxx format)" }),
    }),
    async execute(_id: string, params: { workspace_id: string; table_id: string; column_id: string }) {
      await client.deleteTableColumn(params.workspace_id, params.table_id, params.column_id);
      return textResult("Column deleted.");
    },
  });

  api.registerTool({
    name: "octopus_update_table",
    description: "Rename a table or change its description",
    label: "Update a Octopus table",
    parameters: Type.Object({
      workspace_id: Type.String({ description: "Workspace UUID" }),
      table_id: Type.String({ description: "Table UUID" }),
      name: Type.Optional(Type.String({ description: "New name" })),
      description: Type.Optional(Type.String({ description: "New description" })),
    }),
    async execute(_id: string, params: { workspace_id: string; table_id: string; name?: string; description?: string }) {
      const data: Record<string, unknown> = {};
      if (params.name) data.name = params.name;
      if (params.description) data.description = params.description;
      const result = await client.updateTable(params.workspace_id, params.table_id, data);
      return textResult(JSON.stringify(result, null, 2));
    },
  });

  api.registerTool({
    name: "octopus_update_table_column",
    description: "Rename a column, change its type, or update options",
    label: "Update a column in a Octopus table",
    parameters: Type.Object({
      workspace_id: Type.String({ description: "Workspace UUID" }),
      table_id: Type.String({ description: "Table UUID" }),
      column_id: Type.String({ description: "Column ID (col_xxx format)" }),
      name: Type.Optional(Type.String({ description: "New name" })),
      column_type: Type.Optional(Type.String({ description: "New type" })),
      options: Type.Optional(Type.String({ description: "Comma-separated options for select/multiselect" })),
    }),
    async execute(
      _id: string,
      params: { workspace_id: string; table_id: string; column_id: string; name?: string; column_type?: string; options?: string },
    ) {
      const data: Record<string, unknown> = {};
      if (params.name) data.name = params.name;
      if (params.column_type) data.type = params.column_type;
      if (params.options) data.options = params.options.split(",").map((o) => o.trim()).filter(Boolean);
      const result = await client.updateTableColumn(params.workspace_id, params.table_id, params.column_id, data);
      return textResult(JSON.stringify(result, null, 2));
    },
  });

  api.registerTool({
    name: "octopus_update_table_rows_batch",
    description:
      "Batch update rows. rows is JSON: [{\"row_id\":\"...\",\"data\":{\"Status\":\"done\"}}]. " +
      "Data keys can be column names (auto-resolved to IDs).",
    label: "Batch update rows in a Octopus table",
    parameters: Type.Object({
      workspace_id: Type.String({ description: "Workspace UUID" }),
      table_id: Type.String({ description: "Table UUID" }),
      rows: Type.String({ description: "JSON array of {row_id, data} objects" }),
    }),
    async execute(_id: string, params: { workspace_id: string; table_id: string; rows: string }) {
      const rowsData = JSON.parse(params.rows) as { row_id: string; data: Record<string, unknown> }[];
      const table = (await client.getTable(params.workspace_id, params.table_id)) as any;
      const cols = table.columns ?? [];
      const nameToId: Record<string, string> = {};
      const idSet = new Set<string>();
      for (const col of cols) { nameToId[col.name] = col.id; idSet.add(col.id); }
      const resolved = rowsData.map((item) => {
        const rd: Record<string, unknown> = {};
        for (const [k, v] of Object.entries(item.data)) {
          if (idSet.has(k)) rd[k] = v;
          else if (nameToId[k]) rd[nameToId[k]] = v;
        }
        return { row_id: item.row_id, data: rd };
      });
      const result = await client.updateTableRowsBatch(params.workspace_id, params.table_id, resolved);
      return textResult(JSON.stringify(result, null, 2));
    },
  });

  api.registerTool({
    name: "octopus_count_table_rows",
    description: "Count rows matching optional filters without fetching data",
    label: "Count rows in a Octopus table",
    parameters: Type.Object({
      workspace_id: Type.String({ description: "Workspace UUID" }),
      table_id: Type.String({ description: "Table UUID" }),
      filters: Type.Optional(Type.String({ description: "JSON array of filter objects" })),
    }),
    async execute(_id: string, params: { workspace_id: string; table_id: string; filters?: string }) {
      const result = await client.countTableRows(params.workspace_id, params.table_id, params.filters ?? "");
      return textResult(JSON.stringify(result, null, 2));
    },
  });
}
