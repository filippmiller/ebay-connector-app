import React, { useMemo, useState } from 'react';
import FixedHeader from '@/components/FixedHeader';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import api from '@/lib/apiClient';

type MainTab = 'mssql-database' | 'temp' | 'worker';
type DetailTab = 'columns' | 'preview';

interface MssqlConnectionConfig {
  host: string; // kept for type compatibility, but backend will use env defaults when blank
  port: number;
  database: string;
  username: string;
  password: string;
  encrypt: boolean;
}

interface MssqlSchemaTreeResponse {
  database: string;
  schemas: {
    name: string;
    tables: { name: string }[];
  }[];
}

interface MssqlColumnInfo {
  name: string;
  dataType: string;
  isNullable: boolean;
  isPrimaryKey: boolean;
  defaultValue: string | null;
}

interface MssqlTablePreviewResponse {
  columns: string[];
  rows: any[][];
  limit: number;
  offset: number;
}

// Minimal Supabase table info used by the Migration Worker tab.
// This matches the shape returned by /api/admin/db/tables for our purposes.
interface TableInfo {
  schema: string;
  name: string;
  row_estimate?: number | null;
}

interface SelectedTable {
  schema: string;
  name: string;
}

const AdminDataMigrationPage: React.FC = () => {
  // SCREEN 1: Global Migration Dashboard shell
  const [activeTab, setActiveTab] = useState<MainTab>('mssql-database');

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      <FixedHeader />
      <div className="pt-12 flex-1 px-4 pb-4">
        <div className="w-full mx-auto flex flex-col">
          <h1 className="text-2xl font-bold mb-2">Admin &rarr; Data Migration</h1>
          <p className="text-sm text-gray-600 mb-4 max-w-3xl">
            Internal admin-only workspace for exploring an external MSSQL database (schemas, tables, columns, and sample
            data) and mapping it into Supabase. Credentials are never stored and are sent only to backend admin endpoints
            for the current admin session.
          </p>

          {/* Global modes: legacy MSSQL explorer vs new Dual-DB Migration Studio */}
          <div className="flex gap-2 mb-4">
            <Button
              variant={activeTab === 'mssql-database' ? 'default' : 'outline'}
              size="sm"
              onClick={() => setActiveTab('mssql-database')}
            >
              MSSQL Explorer (legacy)
            </Button>
            <Button
              variant={activeTab === 'temp' ? 'default' : 'outline'}
              size="sm"
              onClick={() => setActiveTab('temp')}
            >
              Dual-DB Migration Studio
            </Button>
            <Button
              variant={activeTab === 'worker' ? 'default' : 'outline'}
              size="sm"
              onClick={() => setActiveTab('worker')}
            >
              Worker
            </Button>
          </div>

          <div className="flex-1 min-h-0">
            {activeTab === 'mssql-database' && <MssqlDatabaseTab />}
            {activeTab === 'temp' && <DualDbMigrationStudioShell />}
            {activeTab === 'worker' && <MigrationWorkerTab />}
          </div>
        </div>
      </div>
    </div>
  );
};

const MssqlDatabaseTab: React.FC = () => {
  const [config, setConfig] = useState<MssqlConnectionConfig>({
    host: '', // credentials are provided by the backend via environment variables
    port: 1433,
    database: '',
    username: '',
    password: '',
    encrypt: true,
  });
  const [isTesting, setIsTesting] = useState(false);
  const [testOk, setTestOk] = useState<boolean | null>(null);
  const [testMessage, setTestMessage] = useState<string | null>(null);

  const [schemaTree, setSchemaTree] = useState<MssqlSchemaTreeResponse | null>(null);
  const [schemaLoading, setSchemaLoading] = useState(false);
  const [schemaError, setSchemaError] = useState<string | null>(null);
  const [schemaSearch, setSchemaSearch] = useState('');

  const [selectedTable, setSelectedTable] = useState<SelectedTable | null>(null);
  const [detailTab, setDetailTab] = useState<DetailTab>('columns');

  const [columns, setColumns] = useState<MssqlColumnInfo[] | null>(null);
  const [columnsLoading, setColumnsLoading] = useState(false);
  const [columnsError, setColumnsError] = useState<string | null>(null);

  const [preview, setPreview] = useState<MssqlTablePreviewResponse | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewLimit, setPreviewLimit] = useState(50);
  const [previewOffset, setPreviewOffset] = useState(0);
  const [sortColumn, setSortColumn] = useState<string | null>(null);
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc');

  const handleConfigChange = (field: keyof MssqlConnectionConfig, value: string | number | boolean) => {
    setConfig((prev) => ({ ...prev, [field]: value }));
  };

  const handleTestConnection = async () => {
    setIsTesting(true);
    setTestOk(null);
    setTestMessage(null);
    setSchemaTree(null);
    setSelectedTable(null);
    setColumns(null);
    setPreview(null);

    try {
      const resp = await api.post<{ ok: boolean; error?: string }>('/api/admin/mssql/test-connection', config);
      if (resp.data.ok) {
        setTestOk(true);
        setTestMessage('Connection successful. Loading schema tree...');
        await loadSchemaTree();
      } else {
        setTestOk(false);
        setTestMessage(resp.data.error || 'Connection failed');
      }
    } catch (e: any) {
      setTestOk(false);
      const message = e?.response?.data?.detail || e.message || 'Connection failed';
      setTestMessage(message);
    } finally {
      setIsTesting(false);
    }
  };

  const loadSchemaTree = async () => {
    setSchemaLoading(true);
    setSchemaError(null);
    try {
      const resp = await api.post<MssqlSchemaTreeResponse>('/api/admin/mssql/schema-tree', config);
      setSchemaTree(resp.data);
    } catch (e: any) {
      const message = e?.response?.data?.detail || e.message || 'Failed to load schema tree';
      setSchemaError(message);
      setSchemaTree(null);
    } finally {
      setSchemaLoading(false);
    }
  };

  const handleSelectTable = (schema: string, name: string) => {
    setSelectedTable({ schema, name });
    setDetailTab('columns');
    setColumns(null);
    setColumnsError(null);
    setPreview(null);
    setPreviewError(null);
    setPreviewOffset(0);
    loadColumns(schema, name);
  };

  const loadColumns = async (schema: string, table: string) => {
    setColumnsLoading(true);
    setColumnsError(null);
    try {
      const resp = await api.post<MssqlColumnInfo[]>('/api/admin/mssql/table-columns', {
        ...config,
        schema,
        table,
      });
      setColumns(resp.data);
    } catch (e: any) {
      const message = e?.response?.data?.detail || e.message || 'Failed to load table columns';
      setColumnsError(message);
      setColumns(null);
    } finally {
      setColumnsLoading(false);
    }
  };

  const loadPreview = async (schema: string, table: string, limit: number, offset: number) => {
    setPreviewLoading(true);
    setPreviewError(null);
    try {
      const resp = await api.post<MssqlTablePreviewResponse>('/api/admin/mssql/table-preview', {
        ...config,
        schema,
        table,
        limit,
        offset,
      });
      setPreview(resp.data);
    } catch (e: any) {
      const message = e?.response?.data?.detail || e.message || 'Failed to load table preview';
      setPreviewError(message);
      setPreview(null);
    } finally {
      setPreviewLoading(false);
    }
  };

  const filteredSchemas = useMemo(() => {
    if (!schemaTree) return [];
    const q = schemaSearch.trim().toLowerCase();
    if (!q) return schemaTree.schemas;
    return schemaTree.schemas
      .map((s) => ({
        ...s,
        tables: s.tables.filter((t) => t.name.toLowerCase().includes(q) || `${s.name}.${t.name}`.toLowerCase().includes(q)),
      }))
      .filter((s) => s.tables.length > 0);
  }, [schemaTree, schemaSearch]);

  const sortedPreviewRows = useMemo(() => {
    if (!preview || !preview.columns.length || !preview.rows.length || !sortColumn) return preview?.rows || [];
    const idx = preview.columns.indexOf(sortColumn);
    if (idx === -1) return preview.rows;
    const rowsCopy = [...preview.rows];
    rowsCopy.sort((a, b) => {
      const av = a[idx];
      const bv = b[idx];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      if (av === bv) return 0;
      if (av > bv) return sortDirection === 'asc' ? 1 : -1;
      return sortDirection === 'asc' ? -1 : 1;
    });
    return rowsCopy;
  }, [preview, sortColumn, sortDirection]);

  const handleHeaderClick = (col: string) => {
    if (!preview) return;
    if (sortColumn === col) {
      setSortDirection((prev) => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortColumn(col);
      setSortDirection('asc');
    }
  };

  const handlePreviewTab = () => {
    setDetailTab('preview');
    if (selectedTable && !preview) {
      loadPreview(selectedTable.schema, selectedTable.name, previewLimit, previewOffset);
    }
  };

  const handleChangeLimit = (newLimit: number) => {
    setPreviewLimit(newLimit);
    setPreviewOffset(0);
    if (selectedTable) {
      loadPreview(selectedTable.schema, selectedTable.name, newLimit, 0);
    }
  };

  const handleNextPage = () => {
    if (!selectedTable) return;
    const newOffset = previewOffset + previewLimit;
    setPreviewOffset(newOffset);
    loadPreview(selectedTable.schema, selectedTable.name, previewLimit, newOffset);
  };

  const handlePrevPage = () => {
    if (!selectedTable) return;
    const newOffset = Math.max(0, previewOffset - previewLimit);
    setPreviewOffset(newOffset);
    loadPreview(selectedTable.schema, selectedTable.name, previewLimit, newOffset);
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Database Connection</CardTitle>
          <CardDescription>
            Connect to the legacy MSSQL database. Host, username, and password are already configured on the server (Railway
            environment variables); you only need to specify which database to explore.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
            <div className="space-y-1">
              <label className="block text-xs font-medium text-gray-700">Database</label>
              <input
                type="text"
                className="w-full border rounded px-2 py-1 text-sm"
                value={config.database}
                onChange={(e) => handleConfigChange('database', e.target.value)}
                placeholder="DB_A28F26_parts"
              />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Button size="sm" onClick={handleTestConnection} disabled={isTesting}>
              {isTesting ? 'Testing connection...' : 'Test connection'}
            </Button>
            {testOk === true && testMessage && (
              <span className="text-xs text-green-700 font-medium">{testMessage}</span>
            )}
            {testOk === false && testMessage && (
              <span className="text-xs text-red-700 font-medium">{testMessage}</span>
            )}
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-12 gap-4">
        <div className="col-span-12 md:col-span-4 border rounded bg-white p-3 flex flex-col min-h-[300px]">
          <div className="flex items-center justify-between mb-2">
            <div className="font-semibold text-sm">Schema tree</div>
            {schemaLoading && <div className="text-xs text-gray-500">Loading...</div>}
          </div>
          <div className="mb-2">
            <input
              type="text"
              value={schemaSearch}
              onChange={(e) => setSchemaSearch(e.target.value)}
              placeholder="Search tables..."
              className="w-full border rounded px-2 py-1 text-sm"
            />
          </div>
          {schemaError && <div className="mb-2 text-xs text-red-600">{schemaError}</div>}
          {!schemaTree && !schemaLoading && (
            <div className="text-xs text-gray-500 mt-2">
              Test a connection to load MSSQL schemas and tables.
            </div>
          )}
          {schemaTree && (
            <div className="flex-1 overflow-auto border rounded p-2 text-xs">
              <div className="font-mono text-[11px] mb-1 text-gray-700">{schemaTree.database}</div>
              {filteredSchemas.length === 0 && (
                <div className="text-[11px] text-gray-500">No tables match the search.</div>
              )}
              {filteredSchemas.map((s) => (
                <div key={s.name} className="mb-1">
                  <div className="font-mono text-[11px] font-semibold text-gray-800">{s.name}</div>
                  <div className="ml-3">
                    {s.tables.map((t) => {
                      const isSelected =
                        selectedTable?.schema === s.name && selectedTable?.name === t.name;
                      return (
                        <div
                          key={t.name}
                          className={`cursor-pointer px-1 py-0.5 rounded border-b border-dotted border-gray-100 hover:bg-blue-50 ${
                            isSelected ? 'bg-blue-100 font-semibold' : ''
                          }`}
                          onClick={() => handleSelectTable(s.name, t.name)}
                        >
                          <span className="font-mono text-[11px]">{t.name}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="col-span-12 md:col-span-8 border rounded bg-white p-3 min-h-[300px]">
          {!selectedTable ? (
            <div className="h-full flex items-center justify-center text-sm text-gray-500">
              Select a table in the schema tree to see columns and sample data.
            </div>
          ) : (
            <div className="flex flex-col h-full">
              <div className="flex items-center justify-between mb-2">
                <div>
                  <div className="font-mono text-sm">
                    {selectedTable.schema}.{selectedTable.name}
                  </div>
                </div>
                <div className="flex gap-2 text-sm">
                  <button
                    className={`px-3 py-1 rounded border text-xs ${
                      detailTab === 'columns' ? 'bg-blue-600 text-white' : 'bg-white text-gray-700'
                    }`}
                    onClick={() => setDetailTab('columns')}
                  >
                    Columns
                  </button>
                  <button
                    className={`px-3 py-1 rounded border text-xs ${
                      detailTab === 'preview' ? 'bg-blue-600 text-white' : 'bg-white text-gray-700'
                    }`}
                    onClick={handlePreviewTab}
                  >
                    Preview data
                  </button>
                </div>
              </div>

              <div className="flex-1 overflow-auto mt-2">
                {detailTab === 'columns' ? (
                  <ColumnsView
                    loading={columnsLoading}
                    error={columnsError}
                    columns={columns}
                    onReload={() =>
                      selectedTable && loadColumns(selectedTable.schema, selectedTable.name)
                    }
                  />
                ) : (
                  <PreviewView
                    preview={preview}
                    loading={previewLoading}
                    error={previewError}
                    limit={previewLimit}
                    offset={previewOffset}
                    onReload={() =>
                      selectedTable &&
                      loadPreview(selectedTable.schema, selectedTable.name, previewLimit, previewOffset)
                    }
                    onNext={handleNextPage}
                    onPrev={handlePrevPage}
                    onChangeLimit={handleChangeLimit}
                    sortColumn={sortColumn}
                    sortDirection={sortDirection}
                    onHeaderClick={handleHeaderClick}
                    rows={sortedPreviewRows}
                  />
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

interface ColumnsViewProps {
  loading: boolean;
  error: string | null;
  columns: MssqlColumnInfo | MssqlColumnInfo[] | null;
  onReload: () => void;
}

const ColumnsView: React.FC<ColumnsViewProps> = ({ loading, error, columns, onReload }) => {
  const columnList: MssqlColumnInfo[] | null = Array.isArray(columns)
    ? columns
    : columns
    ? [columns]
    : null;

  if (loading) {
    return <div className="text-sm text-gray-500">Loading columns...</div>;
  }
  if (error) {
    return (
      <div className="space-y-2">
        <div className="text-sm text-red-600">{error}</div>
        <Button size="sm" variant="outline" onClick={onReload}>
          Retry
        </Button>
      </div>
    );
  }
  if (!columnList) {
    return (
      <div className="text-sm text-gray-500">
        No column metadata loaded yet. Click "Columns" again or re-select the table.
      </div>
    );
  }

  return (
    <table className="min-w-full border text-sm">
      <thead className="bg-gray-100">
        <tr>
          <th className="px-2 py-1 border">Column name</th>
          <th className="px-2 py-1 border">Data type</th>
          <th className="px-2 py-1 border">Nullable</th>
          <th className="px-2 py-1 border">PK</th>
          <th className="px-2 py-1 border">Default value</th>
        </tr>
      </thead>
      <tbody>
        {columnList.map((col) => (
          <tr key={col.name}>
            <td className="px-2 py-1 border font-mono text-xs">{col.name}</td>
            <td className="px-2 py-1 border text-xs">{col.dataType}</td>
            <td className="px-2 py-1 border text-xs">{col.isNullable ? 'YES' : 'NO'}</td>
            <td className="px-2 py-1 border text-xs">{col.isPrimaryKey ? 'YES' : ''}</td>
            <td className="px-2 py-1 border text-xs max-w-xs truncate" title={col.defaultValue || undefined}>
              {col.defaultValue}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
};

interface PreviewViewProps {
  preview: MssqlTablePreviewResponse | null;
  loading: boolean;
  error: string | null;
  limit: number;
  offset: number;
  onReload: () => void;
  onNext: () => void;
  onPrev: () => void;
  onChangeLimit: (limit: number) => void;
  sortColumn: string | null;
  sortDirection: 'asc' | 'desc';
  onHeaderClick: (col: string) => void;
  rows: any[][];
}

const PreviewView: React.FC<PreviewViewProps> = ({
  preview,
  loading,
  error,
  limit,
  offset,
  onReload,
  onNext,
  onPrev,
  onChangeLimit,
  sortColumn,
  sortDirection,
  onHeaderClick,
  rows,
}) => {
  if (loading) {
    return <div className="text-sm text-gray-500">Loading preview...</div>;
  }
  if (error) {
    return (
      <div className="space-y-2">
        <div className="text-sm text-red-600">{error}</div>
        <Button size="sm" variant="outline" onClick={onReload}>
          Retry
        </Button>
      </div>
    );
  }
  if (!preview || !preview.columns.length || !rows.length) {
    return <div className="text-sm text-gray-500">No preview data loaded yet.</div>;
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-xs text-gray-600">
        <div>
          Rows {offset + 1}–{offset + rows.length} (limit {limit})
        </div>
        <div className="flex items-center gap-2">
          <span>Limit:</span>
          <select
            className="border rounded px-1 py-0.5 text-xs"
            value={limit}
            onChange={(e) => onChangeLimit(Number(e.target.value) || 50)}
          >
            <option value={20}>20</option>
            <option value={50}>50</option>
            <option value={100}>100</option>
            <option value={200}>200</option>
          </select>
          <div className="flex gap-1">
            <Button size="sm" variant="outline" disabled={offset === 0} onClick={onPrev}>
              Previous
            </Button>
            <Button size="sm" variant="outline" disabled={rows.length < limit} onClick={onNext}>
              Next
            </Button>
          </div>
        </div>
      </div>
      <div className="overflow-auto border rounded max-h-[60vh]">
        <table className="min-w-full text-xs table-fixed">
          <thead className="bg-gray-100">
            <tr>
              {preview.columns.map((col) => (
                <th
                  key={col}
                  className="px-2 py-1 border text-left font-mono text-[11px] cursor-pointer select-none"
                  onClick={() => onHeaderClick(col)}
                >
                  {col}
                  {sortColumn === col && (sortDirection === 'asc' ? ' ▲' : ' ▼')}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, idx) => (
              <tr key={idx} className="border-t">
                {preview.columns.map((col, colIdx) => (
                  <td
                    key={col}
                    className="px-2 py-1 border whitespace-nowrap max-w-xs overflow-x-auto text-[11px] font-mono"
                  >
                    <div className="inline-block whitespace-pre select-text">
                      {row[colIdx] === null || row[colIdx] === undefined
                        ? ''
                        : typeof row[colIdx] === 'object'
                        ? JSON.stringify(row[colIdx], null, 2)
                        : String(row[colIdx])}
                    </div>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

// SCREEN 2: Dual-DB Migration Studio main shell (3-column layout)
const DualDbMigrationStudioShell: React.FC = () => {
  // Reuse MSSQL connection config from the legacy tab shape, but keep it local to this component.
  const [config, setConfig] = useState<MssqlConnectionConfig>({
    host: '', // credentials are provided by the backend via environment variables
    port: 1433,
    database: '',
    username: '',
    password: '',
    encrypt: true,
  });

  const [isTesting, setIsTesting] = useState(false);
  const [testOk, setTestOk] = useState<boolean | null>(null);
  const [testMessage, setTestMessage] = useState<string | null>(null);

  const [schemaTree, setSchemaTree] = useState<MssqlSchemaTreeResponse | null>(null);
  const [schemaLoading, setSchemaLoading] = useState(false);
  const [schemaError, setSchemaError] = useState<string | null>(null);
  const [schemaSearch, setSchemaSearch] = useState('');
  const [selectedSourceTable, setSelectedSourceTable] = useState<SelectedTable | null>(null);

  // Supabase (target) summary, reusing AdminDbExplorer endpoints
  interface TargetTableInfo {
    schema: string;
    name: string;
    row_estimate: number | null;
  }

  interface TargetColumnInfo {
    name: string;
    data_type: string;
    is_nullable: boolean;
    is_primary_key: boolean;
    is_foreign_key: boolean;
    default: string | null;
  }

  interface TargetSchemaResponse {
    schema: string;
    name: string;
    columns: TargetColumnInfo[];
  }

  const [targetTables, setTargetTables] = useState<TargetTableInfo[]>([]);
  const [targetSearch, setTargetSearch] = useState('');
  const [targetTablesLoading, setTargetTablesLoading] = useState(false);
  const [targetError, setTargetError] = useState<string | null>(null);
  const [selectedTargetTable, setSelectedTargetTable] = useState<TargetTableInfo | null>(null);
  const [targetSchema, setTargetSchema] = useState<TargetSchemaResponse | null>(null);

  // Basic mapping summary state (stubbed for now)
  interface MappingRow {
    sourceColumn: string;
    sourceType: string;
    targetColumn: string | null;
    targetType: string | null;
    status: 'auto-mapped' | 'missing' | 'needs-review';
  }

  const [mappingRows, setMappingRows] = useState<MappingRow[]>([]);
  const [isConfirmOneToOneOpen, setIsConfirmOneToOneOpen] = useState(false);

  // Planned 1:1 target for new-table flow (Flow A) or existing-table flow (Flow B).
  const [plannedTargetTable, setPlannedTargetTable] = useState<{ schema: string; name: string } | null>(null);
  const [oneToOneMode, setOneToOneMode] = useState<'new-table' | 'existing'>('existing');

  // Flow A (new Supabase table) dialog state
  const [isCreateNewTableOpen, setIsCreateNewTableOpen] = useState(false);
  const [newTableName, setNewTableName] = useState('');
  const [newTableSchema, setNewTableSchema] = useState('public');
  const [newTableColumns, setNewTableColumns] = useState<MssqlColumnInfo[] | null>(null);

  // 1:1 backend job state
  const [isRunningOneToOne, setIsRunningOneToOne] = useState(false);
  const [oneToOneResult, setOneToOneResult] = useState<any | null>(null);
  const [oneToOneError, setOneToOneError] = useState<string | null>(null);
  const [oneToOneJobId, setOneToOneJobId] = useState<string | null>(null);
  const [oneToOneJobStatus, setOneToOneJobStatus] = useState<any | null>(null);

  // Latest records modal state
  const [latestOpen, setLatestOpen] = useState(false);
  const [latestTitle, setLatestTitle] = useState('');
  const [latestColumns, setLatestColumns] = useState<string[]>([]);
  const [latestRows, setLatestRows] = useState<any[][]>([]);
  const [latestLoading, setLatestLoading] = useState(false);
  const [latestError, setLatestError] = useState<string | null>(null);

  const handleConfigChange = (field: keyof MssqlConnectionConfig, value: string | number | boolean) => {
    setConfig((prev) => ({ ...prev, [field]: value }));
  };

  const handleTestConnection = async () => {
    setIsTesting(true);
    setTestOk(null);
    setTestMessage(null);
    setSchemaTree(null);
    setSelectedSourceTable(null);

    try {
      const resp = await api.post<{ ok: boolean; error?: string; message?: string }>(
        '/api/admin/mssql/test-connection',
        config,
      );
      if (resp.data.ok) {
        setTestOk(true);
        setTestMessage(resp.data.message || 'Connection successful. Loading schema tree...');
        await loadSchemaTree();
      } else {
        setTestOk(false);
        setTestMessage(resp.data.error || 'Connection failed');
      }
    } catch (e: any) {
      setTestOk(false);
      const message = e?.response?.data?.detail || e.message || 'Connection failed';
      setTestMessage(message);
    } finally {
      setIsTesting(false);
    }
  };

  const loadSchemaTree = async () => {
    setSchemaLoading(true);
    setSchemaError(null);
    try {
      const resp = await api.post<MssqlSchemaTreeResponse>('/api/admin/mssql/schema-tree', config);
      setSchemaTree(resp.data);
    } catch (e: any) {
      const message = e?.response?.data?.detail || e.message || 'Failed to load schema tree';
      setSchemaError(message);
      setSchemaTree(null);
    } finally {
      setSchemaLoading(false);
    }
  };

  const filteredSchemas = useMemo(() => {
    if (!schemaTree) return [];
    const q = schemaSearch.trim().toLowerCase();
    if (!q) return schemaTree.schemas;
    return schemaTree.schemas
      .map((s) => ({
        ...s,
        tables: s.tables.filter((t) => t.name.toLowerCase().includes(q) || `${s.name}.${t.name}`.toLowerCase().includes(q)),
      }))
      .filter((s) => s.tables.length > 0);
  }, [schemaTree, schemaSearch]);

  const handleSelectSourceTable = (schema: string, name: string) => {
    setSelectedSourceTable({ schema, name });
    // When source or target changes, we rebuild a very simple mapping summary later.
    setMappingRows([]);
    setPlannedTargetTable(null);
  };

  const openLatestForMssql = async (schema: string, name: string) => {
    setLatestOpen(true);
    setLatestTitle(`Latest 50 rows – MSSQL ${schema}.${name}`);
    setLatestColumns([]);
    setLatestRows([]);
    setLatestError(null);
    setLatestLoading(true);
    try {
      const resp = await api.post('/api/admin/mssql/latest-rows', {
        ...config,
        schema,
        table: name,
        limit: 50,
        offset: 0,
      });
      const data = resp.data as { columns: string[]; rows: any[][] };
      setLatestColumns(data.columns || []);
      setLatestRows(data.rows || []);
    } catch (e: any) {
      const message = e?.response?.data?.detail || e.message || 'Failed to load latest MSSQL rows';
      setLatestError(typeof message === 'string' ? message : JSON.stringify(message));
    } finally {
      setLatestLoading(false);
    }
  };

  const loadTargetTables = async () => {
    setTargetTablesLoading(true);
    setTargetError(null);
    try {
      const resp = await api.get<TargetTableInfo[]>('/api/admin/db/tables');
      setTargetTables(resp.data);
    } catch (e: any) {
      setTargetError(e?.response?.data?.detail || e.message || 'Failed to load Supabase tables');
      setTargetTables([]);
    } finally {
      setTargetTablesLoading(false);
    }
  };

  const filteredTargetTables = useMemo(() => {
    const q = targetSearch.trim().toLowerCase();
    if (!q) return targetTables;
    return targetTables.filter((t) => `${t.schema}.${t.name}`.toLowerCase().includes(q) || t.name.toLowerCase().includes(q));
  }, [targetTables, targetSearch]);

  const handleSelectTargetTable = async (table: TargetTableInfo) => {
    setSelectedTargetTable(table);
    setTargetSchema(null);
    try {
      const resp = await api.get<TargetSchemaResponse>(`/api/admin/db/tables/${encodeURIComponent(table.name)}/schema`);
      setTargetSchema(resp.data);
      // SCREEN 2: basic mapping summary auto-matching stub
      if (targetSchema && selectedSourceTable) {
        // will be recomputed in useEffect below
      }
    } catch (e: any) {
      setTargetError(e?.response?.data?.detail || e.message || 'Failed to load Supabase table schema');
    }
  };

  // When both sides are selected and we have column metadata, build a simple mapping summary (name-based).
  React.useEffect(() => {
    if (!selectedSourceTable || !targetSchema) {
      setMappingRows([]);
      return;
    }

    const build = async () => {
      try {
        const resp = await api.post<MssqlColumnInfo[]>('/api/admin/mssql/table-columns', {
          ...config,
          schema: selectedSourceTable.schema,
          table: selectedSourceTable.name,
        });
        const sourceCols = resp.data;
        const rows: MappingRow[] = sourceCols.map((col) => {
          const match = targetSchema.columns.find((c) => c.name.toLowerCase() === col.name.toLowerCase());
          if (!match) {
            return {
              sourceColumn: col.name,
              sourceType: col.dataType,
              targetColumn: null,
              targetType: null,
              status: 'missing',
            };
          }
          const typeMatches = match.data_type.toLowerCase().includes(col.dataType.toLowerCase());
          return {
            sourceColumn: col.name,
            sourceType: col.dataType,
            targetColumn: match.name,
            targetType: match.data_type,
            status: typeMatches ? 'auto-mapped' : 'needs-review',
          };
        });
        setMappingRows(rows);
      } catch (e) {
        // We keep mapping summary best-effort; errors are surfaced in logs only.
        // eslint-disable-next-line no-console
        console.error('Failed to load MSSQL columns for mapping summary', e);
        setMappingRows([]);
      }
    };

    void build();
  }, [selectedSourceTable, targetSchema, config]);

  // 1:1 migration can always start when a MSSQL source table is selected.
  // Target table is optional: if absent, we create a new Supabase table from MSSQL schema (Flow A).
  const canRunOneToOne = Boolean(selectedSourceTable);

  const runOneToOneMigration = async () => {
    if (!selectedSourceTable || !plannedTargetTable) return;
    setIsRunningOneToOne(true);
    setOneToOneError(null);
    setOneToOneResult(null);
    setOneToOneJobStatus(null);
    try {
      // Start async job so we don't hit HTTP/Cloudflare timeouts for very large tables.
      const resp = await api.post('/api/admin/migration/mssql-to-supabase/one-to-one/async', {
        mssql: config,
        source_schema: selectedSourceTable.schema,
        source_table: selectedSourceTable.name,
        target_schema: plannedTargetTable.schema,
        target_table: plannedTargetTable.name,
        mode: oneToOneMode,
      });
      setOneToOneJobId(resp.data.job_id);
      setOneToOneJobStatus(resp.data);
    } catch (e: any) {
      const message = e?.response?.data?.detail || e.message || 'Migration failed to start';
      setOneToOneError(typeof message === 'string' ? message : JSON.stringify(message));
      setIsRunningOneToOne(false);
    }
  };

  // Poll async job status while migration is running.
  React.useEffect(() => {
    if (!oneToOneJobId) return;

    let cancelled = false;

    const poll = async () => {
      try {
        const resp = await api.get(`/api/admin/migration/mssql-to-supabase/one-to-one/jobs/${oneToOneJobId}`);
        if (cancelled) return;
        setOneToOneJobStatus(resp.data);

        const status = resp.data.status as string;
        if (status === 'success') {
          setIsRunningOneToOne(false);
          setOneToOneResult({
            status: 'success',
            mode: resp.data.mode,
            source: resp.data.source,
            target: resp.data.target,
            rows_inserted: resp.data.rows_inserted,
            batches: resp.data.batches,
            source_row_count: resp.data.source_row_count,
            target_row_count_before: resp.data.target_row_count_before,
            target_row_count_after: resp.data.target_row_count_after,
          });
          setOneToOneJobId(null);
          // Reload target tables so any new table shows up.
          await loadTargetTables();
        } else if (status === 'error') {
          setIsRunningOneToOne(false);
          setOneToOneError(resp.data.error_message || 'Migration failed');
          setOneToOneJobId(null);
        }
      } catch (e: any) {
        if (cancelled) return;
        // Do not spam errors; show a concise message.
        const message = e?.response?.data?.detail || e.message || 'Failed to fetch migration status';
        setOneToOneError(typeof message === 'string' ? message : JSON.stringify(message));
        setIsRunningOneToOne(false);
        setOneToOneJobId(null);
      }
    };

    const interval = window.setInterval(poll, 2000);
    // Fire once immediately for faster feedback.
    void poll();

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [oneToOneJobId]);

  const renderOneToOneDialog = () => {
    if (!selectedSourceTable || !plannedTargetTable) return null;

    const sourceLabel = `${selectedSourceTable.schema}.${selectedSourceTable.name}`;
    const targetLabel = `${plannedTargetTable.schema}.${plannedTargetTable.name}`;

    const hasConflicts = mappingRows.some((r) => r.status === 'missing');
    const needsReview = mappingRows.some((r) => r.status === 'needs-review');

    const totalSource = oneToOneJobStatus?.source_row_count ?? oneToOneResult?.source_row_count;
    const inserted = oneToOneJobStatus?.rows_inserted ?? oneToOneResult?.rows_inserted;
    const progressPct =
      typeof totalSource === 'number' && totalSource > 0 && typeof inserted === 'number'
        ? Math.min(100, Math.round((inserted / totalSource) * 100))
        : null;

    return (
      <Dialog open={isConfirmOneToOneOpen} onOpenChange={setIsConfirmOneToOneOpen}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>
              {oneToOneMode === 'new-table' ? 'Confirm 1:1 migration (create new table)' : 'Confirm 1:1 migration'}
            </DialogTitle>
            <DialogDescription>
              {oneToOneMode === 'new-table' ? (
                <>
                  Create new Supabase table <span className="font-mono">{targetLabel}</span> from MSSQL source{' '}
                  <span className="font-mono">{sourceLabel}</span> and migrate data 1:1.
                </>
              ) : (
                <>
                  Migrate table 1:1 from <span className="font-mono">{sourceLabel}</span> (MSSQL) to{' '}
                  <span className="font-mono">{targetLabel}</span> (Supabase).
                </>
              )}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 text-sm text-gray-700">
            <p>
              MSSQL will remain read-only. All writes will go to Supabase. Column names, types, nullability, and defaults
              will be used as-is where possible.
            </p>
            {oneToOneError && (
              <p className="text-xs text-red-700">{oneToOneError}</p>
            )}
            {oneToOneJobStatus && (
              <div className="mt-2 space-y-1 text-xs">
                <p className="text-gray-700">
                  Status: <span className="font-semibold">{oneToOneJobStatus.status}</span>
                  {progressPct != null && ` • ~${progressPct}% complete`}
                </p>
                {typeof totalSource === 'number' && (
                  <p className="text-[11px] text-gray-700">
                    Rows inserted so far: {inserted ?? 0} / {totalSource}
                  </p>
                )}
                {progressPct != null && (
                  <div className="w-full bg-gray-200 rounded h-2 overflow-hidden">
                    <div className="bg-blue-600 h-2" style={{ width: `${progressPct}%` }} />
                  </div>
                )}
              </div>
            )}
            {oneToOneResult && (
              <div className="mt-2 space-y-1 text-xs text-green-700">
                <p>
                  Migration completed: {oneToOneResult.rows_inserted ?? 0} rows inserted in{' '}
                  {oneToOneResult.batches ?? 0} batches into {plannedTargetTable.schema}.{
                    plannedTargetTable.name
                  }
                  .
                </p>
                <p className="text-[11px] text-green-700">
                  Source rows at start: {oneToOneResult.source_row_count ?? 'n/a'}; target rows before:{' '}
                  {oneToOneResult.target_row_count_before ?? 'n/a'}; target rows after:{' '}
                  {oneToOneResult.target_row_count_after ?? 'n/a'}.
                </p>
              </div>
            )}
            {needsReview && (
              <p className="text-xs text-yellow-700">
                Warning: some columns have type differences between MSSQL and Supabase. 1:1 migration may still work but
                you should verify types or use the mapping editor.
              </p>
            )}
            {hasConflicts && (
              <p className="text-xs text-red-700">
                There are required source columns without matching targets. 1:1 migration into the existing table may be
                unsafe. Consider using the mapping editor.
              </p>
            )}
          </div>
          <DialogFooter className="flex justify-end gap-2">
            <Button variant="outline" size="sm" onClick={() => setIsConfirmOneToOneOpen(false)}>
              Cancel
            </Button>
            <Button
              variant={hasConflicts ? 'outline' : 'default'}
              size="sm"
              disabled={isRunningOneToOne}
              onClick={() => {
                void runOneToOneMigration();
              }}
            >
              {isRunningOneToOne ? 'Running migration…' : 'Run 1:1 migration'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    );
  };

  const renderCreateNewTableDialog = () => {
    if (!selectedSourceTable) return null;

    const sourceLabel = `${selectedSourceTable.schema}.${selectedSourceTable.name}`;

    return (
      <Dialog open={isCreateNewTableOpen} onOpenChange={setIsCreateNewTableOpen}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>Migrate MSSQL table as new Supabase table</DialogTitle>
            <DialogDescription>
              Migrate <span className="font-mono">{sourceLabel}</span> into a brand new Supabase table.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 text-sm">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <Label className="text-xs font-medium text-gray-700">New table name</Label>
                <Input
                  className="mt-1 h-8 text-sm"
                  value={newTableName}
                  onChange={(e) => setNewTableName(e.target.value)}
                />
              </div>
              <div>
                <Label className="text-xs font-medium text-gray-700">Supabase schema</Label>
                <Input
                  className="mt-1 h-8 text-sm"
                  value={newTableSchema}
                  onChange={(e) => setNewTableSchema(e.target.value || 'public')}
                />
              </div>
            </div>
            <div>
              <div className="text-xs font-semibold text-gray-700 mb-1">Columns to create</div>
              <div className="border rounded max-h-56 overflow-auto text-xs bg-gray-50">
                {!newTableColumns || newTableColumns.length === 0 ? (
                  <div className="px-3 py-2 text-gray-500">Column metadata is not available.</div>
                ) : (
                  <table className="min-w-full text-[11px]">
                    <thead className="bg-gray-100">
                      <tr>
                        <th className="px-2 py-1 border text-left">Column</th>
                        <th className="px-2 py-1 border text-left">MSSQL type</th>
                        <th className="px-2 py-1 border text-left">Proposed Postgres type</th>
                      </tr>
                    </thead>
                    <tbody>
                      {newTableColumns.map((col) => (
                        <tr key={col.name}>
                          <td className="px-2 py-1 border font-mono">{col.name}</td>
                          <td className="px-2 py-1 border">{col.dataType}</td>
                          <td className="px-2 py-1 border font-mono">{mapMssqlToPostgresType(col.dataType)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          </div>
          <DialogFooter className="flex justify-end gap-2">
            <Button variant="outline" size="sm" onClick={() => setIsCreateNewTableOpen(false)}>
              Cancel
            </Button>
            <Button
              size="sm"
              disabled={!newTableName.trim()}
              onClick={() => {
                if (!selectedSourceTable || !newTableName.trim()) return;
                setPlannedTargetTable({ schema: newTableSchema || 'public', name: newTableName.trim() });
                setIsCreateNewTableOpen(false);
                setIsConfirmOneToOneOpen(true);
              }}
            >
              Continue
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    );
  };

  React.useEffect(() => {
    // Load Supabase tables on mount so the right panel is ready.
    void loadTargetTables();
  }, []);

  // Auto-detect same-name Supabase table when a MSSQL table is selected and no target chosen yet.
  React.useEffect(() => {
    if (!selectedSourceTable || selectedTargetTable || !targetTables.length) return;
    const match = targetTables.find(
      (t) => t.schema === 'public' && t.name.toLowerCase() === selectedSourceTable.name.toLowerCase(),
    );
    if (match) {
      void handleSelectTargetTable(match);
    }
  }, [selectedSourceTable, selectedTargetTable, targetTables]);

  const openLatestForSupabase = async (table: TargetTableInfo) => {
    setLatestOpen(true);
    setLatestTitle(`Latest 50 rows – Supabase ${table.schema}.${table.name}`);
    setLatestColumns([]);
    setLatestRows([]);
    setLatestError(null);
    setLatestLoading(true);
    try {
      const resp = await api.get(`/api/admin/db/tables/${encodeURIComponent(table.name)}/rows`, {
        params: { limit: 50, offset: 0 },
      });
      const data = resp.data as { rows: Record<string, any>[] };
      const rows = data.rows || [];
      if (!rows.length) {
        setLatestColumns([]);
        setLatestRows([]);
      } else {
        const columns = Object.keys(rows[0]);
        setLatestColumns(columns);
        setLatestRows(rows.map((r) => columns.map((c) => r[c])));
      }
    } catch (e: any) {
      const message = e?.response?.data?.detail || e.message || 'Failed to load latest Supabase rows';
      setLatestError(typeof message === 'string' ? message : JSON.stringify(message));
    } finally {
      setLatestLoading(false);
    }
  };

  const mapMssqlToPostgresType = (type: string): string => {
    const t = type.toLowerCase();
    if (t.includes('bigint')) return 'bigint';
    if (t === 'int' || t.includes('int')) return 'integer';
    if (t.includes('decimal') || t.includes('numeric') || t.includes('money')) return 'numeric';
    if (t.includes('date') || t.includes('time')) return 'timestamp';
    if (t.includes('bit')) return 'boolean';
    if (t.includes('char') || t.includes('text') || t.includes('nchar') || t.includes('nvarchar')) return 'text';
    return 'text';
  };

  const handleOneToOneClick = async () => {
    if (!selectedSourceTable) return;

    setOneToOneResult(null);
    setOneToOneError(null);

    // Flow B: existing Supabase table explicitly selected.
    if (selectedTargetTable) {
      setOneToOneMode('existing');
      setPlannedTargetTable({ schema: selectedTargetTable.schema, name: selectedTargetTable.name });
      setIsConfirmOneToOneOpen(true);
      return;
    }

    // Flow A: create new Supabase table from MSSQL schema.
    try {
      // Load MSSQL columns for the selected source table.
      const resp = await api.post<MssqlColumnInfo[]>('/api/admin/mssql/table-columns', {
        ...config,
        schema: selectedSourceTable.schema,
        table: selectedSourceTable.name,
      });
      const sourceCols = resp.data;
      setNewTableColumns(sourceCols);
      setNewTableName(selectedSourceTable.name.toLowerCase());
      setNewTableSchema('public');
      setOneToOneMode('new-table');
      setIsCreateNewTableOpen(true);
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error('Failed to load MSSQL columns for new-table 1:1 flow', e);
    }
  };

  const showConnectionOverlay = !testOk && !schemaTree && !schemaLoading;

  const hasSource = Boolean(selectedSourceTable);
  const hasTarget = Boolean(selectedTargetTable);
  let oneToOneHint = 'Select a MSSQL table on the left.';
  if (hasSource && !hasTarget) {
    oneToOneHint =
      "Click 'Migrate 1:1' to create a NEW Supabase table from this MSSQL table, or select a target on the right to use an existing table.";
  } else if (hasSource && hasTarget) {
    oneToOneHint =
      "You selected source and target tables. Click 'Migrate 1:1' to migrate into the existing Supabase table, or open 'Configure mapping…' for custom mapping.";
  }

  return (
    <div className="space-y-4">
      {/* Keep the small MSSQL connection fields at the top */}
      <Card>
        <CardHeader>
          <CardTitle>Database Connection</CardTitle>
          <CardDescription>
            Connect to the legacy MSSQL database for migration. Host, username, and password are already configured on the
            server (Railway environment variables); you only need to specify which database to use.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap items-end gap-4 mb-4">
            <div className="space-y-1 w-full sm:w-56">
              <Label className="block text-xs font-medium text-gray-700">Database</Label>
              <Input
                type="text"
                value={config.database}
                onChange={(e) => handleConfigChange('database', e.target.value)}
                placeholder="DB_A28F26_parts"
                className="h-8 text-sm"
              />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Button size="sm" onClick={handleTestConnection} disabled={isTesting}>
              {isTesting ? 'Testing connection...' : 'Test connection'}
            </Button>
            {testOk === true && testMessage && (
              <span className="text-xs text-green-700 font-medium">{testMessage}</span>
            )}
            {testOk === false && testMessage && (
              <span className="text-xs text-red-700 font-medium">{testMessage}</span>
            )}
          </div>
        </CardContent>
      </Card>

      {/* SCREEN 2: Main 3-column layout */}
      <Card className="w-full">
        <CardHeader>
          <CardTitle className="text-lg">Dual-DB Migration Studio</CardTitle>
          <CardDescription className="text-sm">
            MSSQL on the left, mapping actions in the middle, Supabase target on the right.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col md:flex-row gap-6">
            {/* LEFT: MSSQL source */}
            <div className="md:w-1/3 border rounded bg-white p-4 flex flex-col min-h-[360px] relative">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <div className="font-semibold text-base">MSSQL (legacy)</div>
                  <div className="text-xs text-gray-500">
                    {testOk ? 'Connected' : 'Not connected'}
                  </div>
                </div>
                {schemaLoading && <div className="text-xs text-gray-500">Loading schema...</div>}
              </div>
              <Input
                placeholder="Search tables..."
                value={schemaSearch}
                onChange={(e) => setSchemaSearch(e.target.value)}
                className="mb-2 h-8 text-sm"
              />
              {schemaError && <div className="mb-2 text-[11px] text-red-600">{schemaError}</div>}
              {schemaTree && (
                <div className="flex-1 overflow-auto border rounded p-2 text-sm">
                  <div className="font-mono text-xs mb-1 text-gray-700">{schemaTree.database}</div>
                  {filteredSchemas.length === 0 && (
                    <div className="text-xs text-gray-500">No tables match the search.</div>
                  )}
                  {filteredSchemas.map((s) => (
                    <div key={s.name} className="mb-1">
                      <div className="font-mono text-[11px] font-semibold text-gray-800">{s.name}</div>
                      <div className="ml-3">
                        {s.tables.map((t) => {
                          const isSelected =
                            selectedSourceTable?.schema === s.name && selectedSourceTable?.name === t.name;
                          return (
                            <div
                              key={t.name}
                              className={`flex items-center justify-between gap-2 cursor-pointer px-1 py-0.5 rounded border-b border-dotted border-gray-100 hover:bg-blue-50 ${
                                isSelected ? 'bg-blue-100 font-semibold' : ''
                              }`}
                              onClick={() => handleSelectSourceTable(s.name, t.name)}
                            >
                              <span className="font-mono text-[11px] flex-1 truncate">{t.name}</span>
                              <button
                                type="button"
                                className="text-[10px] px-1.5 py-0.5 border rounded bg-white hover:bg-gray-50"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  void openLatestForMssql(s.name, t.name);
                                }}
                              >
                                Latest 50
                              </button>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {showConnectionOverlay && (
                <div className="absolute inset-0 bg-white/70 flex flex-col items-center justify-center text-sm text-gray-600 gap-2">
                  {/* STATE 2a: No MSSQL connection / error overlay */}
                  <div className="font-medium">Connect to MSSQL first</div>
                  <Button size="sm" variant="outline" onClick={handleTestConnection} disabled={isTesting}>
                    {isTesting ? 'Testing...' : 'Test connection'}
                  </Button>
                </div>
              )}
            </div>

            {/* CENTER: Mapping summary & actions */}
            <div className="md:w-1/3 border rounded bg-white p-4 flex flex-col min-h-[360px]">
              <div className="flex items-center justify-between mb-3">
                <div className="font-semibold text-base">Mapping / Actions</div>
              </div>
              <div className="flex gap-3 mb-4 flex-wrap">
                <Button
                  size="sm"
                  disabled={!canRunOneToOne}
                  onClick={() => {
                    if (!canRunOneToOne) return;
                    // Decide between Flow A (new table) and Flow B (existing table)
                    void handleOneToOneClick();
                  }}
                >
                  Migrate 1:1 (structure + data)
                </Button>
                <Button size="sm" variant="outline" disabled={!selectedSourceTable || !selectedTargetTable}>
                  Configure mapping…
                </Button>
              </div>
              <div className="mb-3 text-sm text-gray-700 space-y-1">
                <div>
                  <span className="font-semibold">Source:</span>{' '}
                  {selectedSourceTable ? (
                    <span className="font-mono">
                      {selectedSourceTable.schema}.{selectedSourceTable.name}
                    </span>
                  ) : (
                    <span className="text-gray-500">Select a table on the left</span>
                  )}
                </div>
                <div>
                  <span className="font-semibold">Target:</span>{' '}
                  {selectedTargetTable ? (
                    <span className="font-mono">
                      {selectedTargetTable.schema}.{selectedTargetTable.name}
                    </span>
                  ) : (
                    <span className="text-gray-500">(no Supabase table selected yet)</span>
                  )}
                </div>
                <p className="text-xs text-gray-500 mt-1">{oneToOneHint}</p>
              </div>

              <div className="flex-1 overflow-auto border rounded">
                <table className="min-w-full text-sm">
                  <thead className="bg-gray-100">
                    <tr>
                      <th className="px-2 py-1 border text-left">Source column</th>
                      <th className="px-2 py-1 border text-left">Type (MSSQL)</th>
                      <th className="px-2 py-1 border text-left">Target column</th>
                      <th className="px-2 py-1 border text-left">Type (Supabase)</th>
                      <th className="px-2 py-1 border text-left">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {mappingRows.length === 0 && (
                      <tr>
                        <td colSpan={5} className="px-2 py-4 text-center text-sm text-gray-500">
                          Mapping summary will appear after you select both source and target tables.
                        </td>
                      </tr>
                    )}
                    {mappingRows.map((row) => (
                      <tr key={row.sourceColumn} className="border-t">
                        <td className="px-2 py-1 border font-mono">{row.sourceColumn}</td>
                        <td className="px-2 py-1 border">{row.sourceType}</td>
                        <td className="px-2 py-1 border font-mono">{row.targetColumn ?? '-'}</td>
                        <td className="px-2 py-1 border">{row.targetType ?? '-'}</td>
                        <td className="px-2 py-1 border">
                          {row.status === 'auto-mapped' && (
                            <span className="text-xs text-green-700 font-medium">auto mapped</span>
                          )}
                          {row.status === 'missing' && (
                            <span className="text-xs text-red-700 font-medium">missing</span>
                          )}
                          {row.status === 'needs-review' && (
                            <span className="text-xs text-yellow-700 font-medium">needs review</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="mt-3 flex gap-2 text-xs text-gray-500">
                <Button size="sm" variant="outline" disabled>
                  Compare schemas (stub)
                </Button>
                <span>Schema compare and full mapping screens will live here (Screens 3–4).</span>
              </div>
            </div>

            {/* RIGHT: Supabase target */}
            <div className="md:w-1/3 border rounded bg-white p-4 flex flex-col min-h-[360px]">
              <div className="flex items-center justify-between mb-3">
                <div className="font-semibold text-base">Supabase (target)</div>
                {targetTablesLoading && <div className="text-xs text-gray-500">Loading tables...</div>}
              </div>
              <Input
                placeholder="Search tables..."
                value={targetSearch}
                onChange={(e) => setTargetSearch(e.target.value)}
                className="mb-2 h-8 text-sm"
              />
              {targetError && <div className="mb-2 text-xs text-red-600">{targetError}</div>}
              <div className="flex-1 overflow-auto border rounded">
                {filteredTargetTables.map((t) => {
                  const isSelected = selectedTargetTable?.schema === t.schema && selectedTargetTable?.name === t.name;
                  return (
                    <div
                      key={`${t.schema}.${t.name}`}
                      className={`w-full px-1 py-0.5 text-xs cursor-pointer border-b border-dotted border-gray-100 hover:bg-blue-50 ${
                        isSelected ? 'bg-blue-50 font-semibold' : ''
                      }`}
                      onClick={() => handleSelectTargetTable(t)}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex-1 min-w-0">
                          <div className="font-mono text-[11px] truncate">{t.name}</div>
                          {t.row_estimate != null && (
                            <div className="text-[10px] text-gray-500">~{Math.round(t.row_estimate)} rows</div>
                          )}
                        </div>
                        <button
                          type="button"
                          className="text-[10px] px-1.5 py-0.5 border rounded bg-white hover:bg-gray-50"
                          onClick={(e) => {
                            e.stopPropagation();
                            void openLatestForSupabase(t);
                          }}
                        >
                          Latest 50
                        </button>
                      </div>
                    </div>
                  );
                })}
                {!targetTablesLoading && filteredTargetTables.length === 0 && (
                  <div className="px-3 py-4 text-sm text-gray-500 text-center">No tables found.</div>
                )}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {renderCreateNewTableDialog()}
      {renderOneToOneDialog()}

      <Dialog open={latestOpen} onOpenChange={setLatestOpen}>
        <DialogContent className="max-w-5xl">
          <DialogHeader>
            <DialogTitle>{latestTitle || 'Latest 50 rows'}</DialogTitle>
          </DialogHeader>
          <div className="text-xs text-gray-600 mb-2">
            This view shows the 50 most recent rows for the selected table, ordered by created_at or primary key when
            available.
          </div>
          {latestError && <div className="text-xs text-red-600 mb-2">{latestError}</div>}
          {latestLoading ? (
            <div className="text-sm text-gray-500">Loading latest rows...</div>
          ) : latestColumns.length === 0 || latestRows.length === 0 ? (
            <div className="text-sm text-gray-500">No rows found.</div>
          ) : (
            <div className="border rounded max-h-[70vh] overflow-x-auto overflow-y-auto">
              <table className="min-w-full text-[11px] table-fixed">
                <thead className="bg-gray-100">
                  <tr>
                    {latestColumns.map((col) => (
                      <th key={col} className="px-2 py-1 border text-left font-mono whitespace-nowrap">
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {latestRows.map((row, idx) => (
                    <tr key={idx} className="border-t">
                      {latestColumns.map((col, colIdx) => (
                        <td key={col} className="px-2 py-1 border align-top max-w-xs">
                          <div className="whitespace-pre-wrap break-all max-h-40 overflow-auto select-text">
                            {row[colIdx] === null || row[colIdx] === undefined
                              ? ''
                              : typeof row[colIdx] === 'object'
                              ? JSON.stringify(row[colIdx], null, 2)
                              : String(row[colIdx])}
                          </div>
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};

interface MigrationWorkerState {
  id: number;
  source_database: string;
  source_schema: string;
  source_table: string;
  target_schema: string;
  target_table: string;
  pk_column: string;
  worker_enabled: boolean;
  interval_seconds: number;
  owner_user_id?: string | null;
  notify_on_success: boolean;
  notify_on_error: boolean;
  last_run_started_at?: string | null;
  last_run_finished_at?: string | null;
  last_run_status?: string | null;
  last_error?: string | null;
  last_source_row_count?: number | null;
  last_target_row_count?: number | null;
  last_inserted_count?: number | null;
  last_max_pk_source?: number | null;
  last_max_pk_target?: number | null;
}

const MigrationWorkerTab: React.FC = () => {
  const [workers, setWorkers] = React.useState<MigrationWorkerState[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [savingId, setSavingId] = React.useState<number | null>(null);
  const [runningId, setRunningId] = React.useState<number | null>(null);

  // New worker dialog state
  const [createOpen, setCreateOpen] = React.useState(false);
  const [createBusy, setCreateBusy] = React.useState(false);
  const [createSourceDatabase, setCreateSourceDatabase] = React.useState('');
  const [createSourceSchema, setCreateSourceSchema] = React.useState('dbo');
  const [createSourceTable, setCreateSourceTable] = React.useState('');
  const [createTargetSchema, setCreateTargetSchema] = React.useState('public');
  const [createTargetTable, setCreateTargetTable] = React.useState('');
  const [createPkColumn, setCreatePkColumn] = React.useState('');
  const [createIntervalSeconds, setCreateIntervalSeconds] = React.useState(300);
  const [createRunImmediately, setCreateRunImmediately] = React.useState(true);

  // MSSQL connection & schema for the New Worker dialog
  const [createMssqlTestOk, setCreateMssqlTestOk] = React.useState<boolean | null>(null);
  const [createMssqlTestMessage, setCreateMssqlTestMessage] = React.useState<string | null>(null);
  const [createMssqlSchemaTree, setCreateMssqlSchemaTree] = React.useState<MssqlSchemaTreeResponse | null>(null);
  const [createMssqlSchemaLoading, setCreateMssqlSchemaLoading] = React.useState(false);
  const [createMssqlSchemaError, setCreateMssqlSchemaError] = React.useState<string | null>(null);
  const [createMssqlTableSearch, setCreateMssqlTableSearch] = React.useState('');

  // Supabase tables for the New Worker dialog
  const [createSupabaseTables, setCreateSupabaseTables] = React.useState<TableInfo[]>([]);
  const [createSupabaseLoading, setCreateSupabaseLoading] = React.useState(false);
  const [createSupabaseError, setCreateSupabaseError] = React.useState<string | null>(null);
  const [createSupabaseSearch, setCreateSupabaseSearch] = React.useState('');

  const buildCreateMssqlConfig = (): MssqlConnectionConfig => ({
    host: '',
    port: 1433,
    database: createSourceDatabase,
    username: '',
    password: '',
    encrypt: true,
  });

  const resetCreateForm = () => {
    setCreateSourceDatabase('');
    setCreateSourceSchema('dbo');
    setCreateSourceTable('');
    setCreateTargetSchema('public');
    setCreateTargetTable('');
    setCreatePkColumn('');
    setCreateIntervalSeconds(300);
    setCreateRunImmediately(true);
    setCreateMssqlTestOk(null);
    setCreateMssqlTestMessage(null);
    setCreateMssqlSchemaTree(null);
    setCreateMssqlSchemaError(null);
    setCreateMssqlTableSearch('');
    setCreateSupabaseError(null);
    setCreateSupabaseSearch('');
  };

  const loadWorkers = async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await api.get<MigrationWorkerState[]>('/api/admin/db-migration/worker/state');
      setWorkers(resp.data);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e.message || 'Failed to load workers');
      setWorkers([]);
    } finally {
      setLoading(false);
    }
  };

  const loadCreateSupabaseTables = async () => {
    if (createSupabaseTables.length > 0) return;
    setCreateSupabaseLoading(true);
    setCreateSupabaseError(null);
    try {
      const resp = await api.get<TableInfo[]>('/api/admin/db/tables');
      setCreateSupabaseTables(resp.data);
    } catch (e: any) {
      setCreateSupabaseError(e?.response?.data?.detail || e.message || 'Failed to load Supabase tables');
      setCreateSupabaseTables([]);
    } finally {
      setCreateSupabaseLoading(false);
    }
  };

  const loadCreateMssqlSchemaTree = async () => {
    if (!createSourceDatabase.trim()) {
      setCreateMssqlSchemaError('Enter MSSQL database name first');
      setCreateMssqlSchemaTree(null);
      return;
    }
    setCreateMssqlSchemaLoading(true);
    setCreateMssqlSchemaError(null);
    try {
      const cfg = buildCreateMssqlConfig();
      const resp = await api.post<MssqlSchemaTreeResponse>('/api/admin/mssql/schema-tree', cfg);
      setCreateMssqlSchemaTree(resp.data);
      setCreateMssqlTestOk(true);
      setCreateMssqlTestMessage('Connection OK. Schema tree loaded.');
    } catch (e: any) {
      setCreateMssqlSchemaTree(null);
      const msg = e?.response?.data?.detail || e.message || 'Failed to load MSSQL schema tree';
      setCreateMssqlSchemaError(msg);
    } finally {
      setCreateMssqlSchemaLoading(false);
    }
  };

  const handleCreateTestConnection = async () => {
    setCreateMssqlTestOk(null);
    setCreateMssqlTestMessage(null);
    setCreateMssqlSchemaTree(null);
    setCreateMssqlSchemaError(null);
    if (!createSourceDatabase.trim()) {
      setCreateMssqlTestOk(false);
      setCreateMssqlTestMessage('Enter MSSQL database name first');
      return;
    }
    try {
      const cfg = buildCreateMssqlConfig();
      const resp = await api.post<{ ok: boolean; error?: string; message?: string }>(
        '/api/admin/mssql/test-connection',
        cfg,
      );
      if (resp.data.ok) {
        setCreateMssqlTestOk(true);
        setCreateMssqlTestMessage(resp.data.message || 'Connection successful. Loading schema tree...');
        await loadCreateMssqlSchemaTree();
      } else {
        setCreateMssqlTestOk(false);
        setCreateMssqlTestMessage(resp.data.error || 'Connection failed');
      }
    } catch (e: any) {
      setCreateMssqlTestOk(false);
      const msg = e?.response?.data?.detail || e.message || 'Connection failed';
      setCreateMssqlTestMessage(msg);
    }
  };

  const createMssqlTableOptions: SelectedTable[] = React.useMemo(() => {
    if (!createMssqlSchemaTree) return [];
    const all: SelectedTable[] = [];
    createMssqlSchemaTree.schemas.forEach((s) => {
      s.tables.forEach((t) => {
        all.push({ schema: s.name, name: t.name });
      });
    });
    const q = createMssqlTableSearch.trim().toLowerCase();
    if (!q) return all.slice(0, 50);
    return all.filter((t) => `${t.schema}.${t.name}`.toLowerCase().includes(q)).slice(0, 50);
  }, [createMssqlSchemaTree, createMssqlTableSearch]);

  const createSupabaseTableOptions: TableInfo[] = React.useMemo(() => {
    const all = createSupabaseTables;
    const q = createSupabaseSearch.trim().toLowerCase();
    if (!q) return all.slice(0, 50);
    return all
      .filter((t) => `${t.schema}.${t.name}`.toLowerCase().includes(q) || t.name.toLowerCase().includes(q))
      .slice(0, 50);
  }, [createSupabaseTables, createSupabaseSearch]);

  React.useEffect(() => {
    void loadWorkers();
  }, []);

  const handleOpenCreate = () => {
    resetCreateForm();
    setError(null);
    setCreateOpen(true);
    // Preload Supabase table list for nicer UX
    void loadCreateSupabaseTables();
  };

  const handleSubmitCreate = async () => {
    if (!createSourceDatabase.trim()) {
      setError('MSSQL database is required.');
      return;
    }
    if (!createSourceSchema.trim() || !createSourceTable.trim()) {
      setError('Select a MSSQL table from the list (test connection first).');
      return;
    }
    if (!createTargetTable.trim()) {
      setError('Supabase target table is required.');
      return;
    }
    setCreateBusy(true);
    setError(null);
    try {
      // Upsert worker (will auto-detect PK if createPkColumn is empty)
      const resp = await api.post<MigrationWorkerState>('/api/admin/db-migration/worker/upsert', {
        source_database: createSourceDatabase.trim(),
        source_schema: createSourceSchema.trim() || 'dbo',
        source_table: createSourceTable.trim(),
        target_schema: createTargetSchema.trim() || 'public',
        target_table: createTargetTable.trim(),
        pk_column: createPkColumn.trim() || undefined,
        worker_enabled: true,
        interval_seconds: createIntervalSeconds || 300,
        owner_user_id: undefined,
        notify_on_success: true,
        notify_on_error: true,
      });
      const worker = resp.data;
      // Optionally run an initial catch-up immediately
      if (createRunImmediately) {
        try {
          await api.post('/api/admin/db-migration/worker/run-once', { id: worker.id, batch_size: 5000 });
        } catch (e: any) {
          // Не считаем это фатальной ошибкой создания; просто покажем сообщение.
          setError(
            e?.response?.data?.detail ||
              e?.message ||
              'Worker was created, but initial run failed. Check logs for details.',
          );
        }
      }
      await loadWorkers();
      setCreateOpen(false);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e.message || 'Failed to create worker');
    } finally {
      setCreateBusy(false);
    }
  };

  const handleToggleEnabled = async (worker: MigrationWorkerState, enabled: boolean) => {
    setSavingId(worker.id);
    setError(null);
    try {
      const resp = await api.post<MigrationWorkerState>('/api/admin/db-migration/worker/upsert', {
        id: worker.id,
        source_database: worker.source_database,
        source_schema: worker.source_schema,
        source_table: worker.source_table,
        target_schema: worker.target_schema,
        target_table: worker.target_table,
        pk_column: worker.pk_column,
        worker_enabled: enabled,
        interval_seconds: worker.interval_seconds,
        owner_user_id: worker.owner_user_id,
        notify_on_success: worker.notify_on_success,
        notify_on_error: worker.notify_on_error,
      });
      setWorkers((prev) => prev.map((w) => (w.id === worker.id ? resp.data : w)));
    } catch (e: any) {
      setError(e?.response?.data?.detail || e.message || 'Failed to update worker');
    } finally {
      setSavingId(null);
    }
  };

  const handleIntervalChange = async (worker: MigrationWorkerState, nextInterval: number) => {
    if (!nextInterval || nextInterval <= 0) return;
    setSavingId(worker.id);
    setError(null);
    try {
      const resp = await api.post<MigrationWorkerState>('/api/admin/db-migration/worker/upsert', {
        id: worker.id,
        source_database: worker.source_database,
        source_schema: worker.source_schema,
        source_table: worker.source_table,
        target_schema: worker.target_schema,
        target_table: worker.target_table,
        pk_column: worker.pk_column,
        worker_enabled: worker.worker_enabled,
        interval_seconds: nextInterval,
        owner_user_id: worker.owner_user_id,
        notify_on_success: worker.notify_on_success,
        notify_on_error: worker.notify_on_error,
      });
      setWorkers((prev) => prev.map((w) => (w.id === worker.id ? resp.data : w)));
    } catch (e: any) {
      setError(e?.response?.data?.detail || e.message || 'Failed to update interval');
    } finally {
      setSavingId(null);
    }
  };

  const handleRunOnce = async (worker: MigrationWorkerState) => {
    setRunningId(worker.id);
    setError(null);
    try {
      await api.post('/api/admin/db-migration/worker/run-once', { id: worker.id, batch_size: 5000 });
      await loadWorkers();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e.message || 'Failed to run worker');
    } finally {
      setRunningId(null);
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between mb-1">
        <div>
          <h2 className="text-sm font-semibold">Migration Workers</h2>
          <p className="text-xs text-gray-600">
            MSSQL→Supabase incremental workers for append-only tables. Each worker periodically pulls new rows based on a
            numeric primary key and appends them into the target table.
          </p>
        </div>
        <Button size="sm" variant="outline" onClick={handleOpenCreate}>
          New worker
        </Button>
      </div>
      {error && <div className="text-xs text-red-600 mb-2">{error}</div>}
      {loading ? (
        <div className="text-sm text-gray-500">Loading workers...</div>
      ) : workers.length === 0 ? (
        <div className="text-sm text-gray-500">No workers configured yet.</div>
      ) : (
        <div className="border rounded bg-white overflow-auto max-h-[60vh] text-xs">
          <table className="min-w-full text-[11px]">
            <thead className="bg-gray-100">
              <tr>
                <th className="px-2 py-1 border text-left">ID</th>
                <th className="px-2 py-1 border text-left">Source</th>
                <th className="px-2 py-1 border text-left">Target</th>
                <th className="px-2 py-1 border text-left">PK column</th>
                <th className="px-2 py-1 border text-left">Enabled</th>
                <th className="px-2 py-1 border text-left">Interval (sec)</th>
                <th className="px-2 py-1 border text-left">Notify OK</th>
                <th className="px-2 py-1 border text-left">Notify errors</th>
                <th className="px-2 py-1 border text-left">Last status</th>
                <th className="px-2 py-1 border text-left">Last run</th>
                <th className="px-2 py-1 border text-left">Last counts</th>
                <th className="px-2 py-1 border text-left">Actions</th>
              </tr>
            </thead>
            <tbody>
              {workers.map((w) => (
                <tr key={w.id} className="border-t align-top">
                  <td className="px-2 py-1 border whitespace-nowrap">{w.id}</td>
                  <td className="px-2 py-1 border whitespace-pre text-[11px] font-mono">
                    {w.source_database}\n{w.source_schema}.{w.source_table}
                  </td>
                  <td className="px-2 py-1 border whitespace-pre text-[11px] font-mono">
                    {w.target_schema}.{w.target_table}
                  </td>
                  <td className="px-2 py-1 border font-mono">{w.pk_column}</td>
                  <td className="px-2 py-1 border">
                    <input
                      type="checkbox"
                      checked={w.worker_enabled}
                      disabled={savingId === w.id}
                      onChange={(e) => handleToggleEnabled(w, e.target.checked)}
                    />
                  </td>
                  <td className="px-2 py-1 border">
                    <input
                      type="number"
                      min={30}
                      className="w-20 border rounded px-1 py-0.5 text-[11px]"
                      value={w.interval_seconds}
                      disabled={savingId === w.id}
                      onChange={(e) => handleIntervalChange(w, Number(e.target.value) || w.interval_seconds)}
                    />
                  </td>
                  <td className="px-2 py-1 border">
                    <input
                      type="checkbox"
                      checked={w.notify_on_success}
                      disabled={savingId === w.id}
                      onChange={(e) =>
                        handleToggleEnabled(
                          { ...w, notify_on_success: e.target.checked },
                          w.worker_enabled,
                        )
                      }
                    />
                  </td>
                  <td className="px-2 py-1 border">
                    <input
                      type="checkbox"
                      checked={w.notify_on_error}
                      disabled={savingId === w.id}
                      onChange={(e) =>
                        handleToggleEnabled(
                          { ...w, notify_on_error: e.target.checked },
                          w.worker_enabled,
                        )
                      }
                    />
                  </td>
                  <td className="px-2 py-1 border">
                    {w.last_run_status ? (
                      <span
                        className={
                          w.last_run_status === 'ok'
                            ? 'text-green-700'
                            : w.last_run_status === 'error'
                            ? 'text-red-700'
                            : 'text-gray-700'
                        }
                      >
                        {w.last_run_status}
                      </span>
                    ) : (
                      <span className="text-gray-400">never</span>
                    )}
                    {w.last_error && (
                      <div className="text-[10px] text-red-600 mt-0.5 max-w-xs truncate" title={w.last_error}>
                        {w.last_error}
                      </div>
                    )}
                  </td>
                  <td className="px-2 py-1 border text-[10px] text-gray-600">
                    {w.last_run_started_at && (
                      <div>start: {w.last_run_started_at}</div>
                    )}
                    {w.last_run_finished_at && (
                      <div>finish: {w.last_run_finished_at}</div>
                    )}
                  </td>
                  <td className="px-2 py-1 border text-[10px] text-gray-700">
                    {w.last_source_row_count != null && (
                      <div>src: {w.last_source_row_count}</div>
                    )}
                    {w.last_target_row_count != null && (
                      <div>tgt: {w.last_target_row_count}</div>
                    )}
                    {w.last_inserted_count != null && (
                      <div>+{w.last_inserted_count} rows</div>
                    )}
                  </td>
                  <td className="px-2 py-1 border">
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7 px-2 text-[11px]"
                      disabled={runningId === w.id}
                      onClick={() => {
                        void handleRunOnce(w);
                      }}
                    >
                      {runningId === w.id ? 'Running…' : 'Run once now'}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>Create migration worker</DialogTitle>
            <DialogDescription>
              Set up an incremental MSSQL→Supabase worker for an append-only table. The worker will periodically pull
              new rows based on a numeric primary key.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 text-xs">
            {/* MSSQL connection */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <Label className="text-[11px]">MSSQL database</Label>
                <Input
                  className="mt-1 h-7 text-[11px]"
                  value={createSourceDatabase}
                  onChange={(e) => setCreateSourceDatabase(e.target.value)}
                  placeholder="DB_A28F26_parts"
                />
                <div className="mt-1 flex items-center gap-2">
                  <Button size="sm" variant="outline" onClick={() => void handleCreateTestConnection()}>
                    Test & load tables
                  </Button>
                  {createMssqlTestOk === true && (
                    <span className="text-[11px] text-green-700">{createMssqlTestMessage || 'OK'}</span>
                  )}
                  {createMssqlTestOk === false && (
                    <span className="text-[11px] text-red-700">{createMssqlTestMessage || 'Connection failed'}</span>
                  )}
                </div>
              </div>
              <div>
                <Label className="text-[11px]">MSSQL schema</Label>
                <Input
                  className="mt-1 h-7 text-[11px]"
                  value={createSourceSchema}
                  onChange={(e) => setCreateSourceSchema(e.target.value || 'dbo')}
                  placeholder="dbo"
                />
                <p className="mt-1 text-[11px] text-gray-500">Used when selecting a table from MSSQL.</p>
              </div>
            </div>

            {/* Source & target table selection */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <Label className="text-[11px]">MSSQL table</Label>
                <Input
                  className="mt-1 h-7 text-[11px]"
                  value={createMssqlTableSearch}
                  onChange={(e) => setCreateMssqlTableSearch(e.target.value)}
                  placeholder="Start typing to search tables, e.g. 'fees'"
                />
                {createMssqlSchemaLoading && (
                  <p className="mt-1 text-[11px] text-gray-500">Loading MSSQL schema...</p>
                )}
                {createMssqlSchemaError && (
                  <p className="mt-1 text-[11px] text-red-600">{createMssqlSchemaError}</p>
                )}
                {createMssqlSchemaTree && createMssqlTableOptions.length > 0 && (
                  <div className="mt-1 max-h-40 overflow-auto border rounded bg-white text-[11px]">
                    {createMssqlTableOptions.map((t) => {
                      const key = `${t.schema}.${t.name}`;
                      const isSelected = t.schema === createSourceSchema && t.name === createSourceTable;
                      return (
                        <button
                          key={key}
                          type="button"
                          className={`w-full text-left px-2 py-0.5 border-b border-dotted border-gray-100 hover:bg-blue-50 ${
                            isSelected ? 'bg-blue-100 font-semibold' : ''
                          }`}
                          onClick={() => {
                            setCreateSourceSchema(t.schema);
                            setCreateSourceTable(t.name);
                            setCreateMssqlTableSearch(`${t.schema}.${t.name}`);
                          }}
                        >
                          <span className="font-mono">{t.schema}.{t.name}</span>
                        </button>
                      );
                    })}
                  </div>
                )}
                {createSourceTable && (
                  <p className="mt-1 text-[11px] text-gray-600">
                    Selected: {createSourceSchema}.{createSourceTable}
                  </p>
                )}
              </div>
              <div>
                <Label className="text-[11px]">Supabase target table</Label>
                <Input
                  className="mt-1 h-7 text-[11px]"
                  value={createSupabaseSearch}
                  onChange={(e) => setCreateSupabaseSearch(e.target.value)}
                  placeholder="Start typing to search tables, e.g. 'fees'"
                />
                {createSupabaseLoading && (
                  <p className="mt-1 text-[11px] text-gray-500">Loading Supabase tables...</p>
                )}
                {createSupabaseError && (
                  <p className="mt-1 text-[11px] text-red-600">{createSupabaseError}</p>
                )}
                {createSupabaseTableOptions.length > 0 && (
                  <div className="mt-1 max-h-40 overflow-auto border rounded bg-white text-[11px]">
                    {createSupabaseTableOptions.map((t) => {
                      const key = `${t.schema}.${t.name}`;
                      const isSelected = t.schema === createTargetSchema && t.name === createTargetTable;
                      return (
                        <button
                          key={key}
                          type="button"
                          className={`w-full text-left px-2 py-0.5 border-b border-dotted border-gray-100 hover:bg-blue-50 ${
                            isSelected ? 'bg-blue-100 font-semibold' : ''
                          }`}
                          onClick={() => {
                            setCreateTargetSchema(t.schema);
                            setCreateTargetTable(t.name);
                            setCreateSupabaseSearch(`${t.schema}.${t.name}`);
                          }}
                        >
                          <span className="font-mono">{t.schema}.{t.name}</span>
                        </button>
                      );
                    })}
                  </div>
                )}
                {createTargetTable && (
                  <p className="mt-1 text-[11px] text-gray-500">
                    Schema: {createTargetSchema || 'public'}. Table: {createTargetTable}
                  </p>
                )}
              </div>
            </div>

            {/* Supabase schema + PK */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <Label className="text-[11px]">Supabase schema</Label>
                <Input
                  className="mt-1 h-7 text-[11px]"
                  value={createTargetSchema}
                  onChange={(e) => setCreateTargetSchema(e.target.value || 'public')}
                  placeholder="public"
                />
              </div>
              <div>
                <Label className="text-[11px]">Primary key column (optional)</Label>
                <Input
                  className="mt-1 h-7 text-[11px]"
                  value={createPkColumn}
                  onChange={(e) => setCreatePkColumn(e.target.value)}
                  placeholder="FeeID (leave blank to auto-detect)"
                />
                <p className="mt-1 text-[11px] text-gray-500">
                  Must be a numeric, monotonically increasing column. If left blank, the system will try to auto-detect a
                  single-column primary key in MSSQL.
                </p>
              </div>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 items-end">
              <div>
                <Label className="text-[11px]">Run every (seconds)</Label>
                <Input
                  type="number"
                  min={30}
                  className="mt-1 h-7 text-[11px] w-32"
                  value={createIntervalSeconds}
                  onChange={(e) => setCreateIntervalSeconds(Number(e.target.value) || 300)}
                />
                <p className="mt-1 text-[11px] text-gray-500">e.g. 300 = every 5 minutes.</p>
              </div>
              <div className="flex items-center gap-2 mt-4">
                <input
                  id="create-worker-run-immediately"
                  type="checkbox"
                  className="h-3 w-3"
                  checked={createRunImmediately}
                  onChange={(e) => setCreateRunImmediately(e.target.checked)}
                />
                <label htmlFor="create-worker-run-immediately" className="text-[11px] text-gray-700">
                  Run initial catch-up immediately after creating the worker
                </label>
              </div>
            </div>
            <p className="text-[11px] text-gray-500">
              On each run, the worker will read MAX(pk) from the Supabase table, then fetch rows from MSSQL where
              pk &gt; MAX(pk) and insert them using ON CONFLICT(pk) DO NOTHING.
            </p>
          </div>
          <DialogFooter className="flex justify-end gap-2 mt-3">
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => {
                if (!createBusy) setCreateOpen(false);
              }}
            >
              Cancel
            </Button>
            <Button
              type="button"
              size="sm"
              disabled={createBusy}
              onClick={() => {
                void handleSubmitCreate();
              }}
            >
              {createBusy ? 'Creating…' : 'Create worker'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default AdminDataMigrationPage;
