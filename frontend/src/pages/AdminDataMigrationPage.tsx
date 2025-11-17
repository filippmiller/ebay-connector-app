import React, { useMemo, useState } from 'react';
import FixedHeader from '@/components/FixedHeader';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import api from '@/lib/apiClient';

type MainTab = 'mssql-database' | 'temp';
type DetailTab = 'columns' | 'preview';

interface MssqlConnectionConfig {
  host: string;
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

interface SelectedTable {
  schema: string;
  name: string;
}

const AdminDataMigrationPage: React.FC = () => {
  // SCREEN 1: Global Migration Dashboard shell
  const [activeTab, setActiveTab] = useState<MainTab>('mssql-database');

  return (
    <div className="min-h-screen bg-gray-50">
      <FixedHeader />
      <div className="pt-12 p-4">
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
        </div>

        {activeTab === 'mssql-database' ? <MssqlDatabaseTab /> : <DualDbMigrationStudioShell />}
      </div>
    </div>
  );
};

const MssqlDatabaseTab: React.FC = () => {
  const [config, setConfig] = useState<MssqlConnectionConfig>({
    host: '',
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
            Connect to an external MSSQL database. Credentials are used only for this session and are never stored in
            Supabase.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
            <div className="space-y-1">
              <label className="block text-xs font-medium text-gray-700">Host / IP</label>
              <input
                type="text"
                className="w-full border rounded px-2 py-1 text-sm"
                value={config.host}
                onChange={(e) => handleConfigChange('host', e.target.value)}
                placeholder="mssql.example.internal"
              />
            </div>
            <div className="space-y-1">
              <label className="block text-xs font-medium text-gray-700">Port</label>
              <input
                type="number"
                className="w-full border rounded px-2 py-1 text-sm"
                value={config.port}
                onChange={(e) => handleConfigChange('port', Number(e.target.value) || 1433)}
                placeholder="1433"
              />
            </div>
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
            <div className="space-y-1">
              <label className="block text-xs font-medium text-gray-700">Username</label>
              <input
                type="text"
                className="w-full border rounded px-2 py-1 text-sm"
                value={config.username}
                onChange={(e) => handleConfigChange('username', e.target.value)}
                placeholder="dbadmin"
              />
            </div>
            <div className="space-y-1">
              <label className="block text-xs font-medium text-gray-700">Password</label>
              <input
                type="password"
                className="w-full border rounded px-2 py-1 text-sm"
                value={config.password}
                onChange={(e) => handleConfigChange('password', e.target.value)}
                placeholder="••••••••"
              />
            </div>
            <div className="flex items-center gap-2 mt-6">
              <input
                id="encrypt"
                type="checkbox"
                className="h-4 w-4"
                checked={config.encrypt}
                onChange={(e) => handleConfigChange('encrypt', e.target.checked)}
              />
              <label htmlFor="encrypt" className="text-xs text-gray-700">
                Use SSL / Encrypt
              </label>
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
    host: '',
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
  const [targetSchemaLoading, setTargetSchemaLoading] = useState(false);

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
      setTargetSchemaLoading(true);
      const resp = await api.get<TargetSchemaResponse>(`/api/admin/db/tables/${encodeURIComponent(table.name)}/schema`);
      setTargetSchema(resp.data);
      // SCREEN 2: basic mapping summary auto-matching stub
      if (targetSchema && selectedSourceTable) {
        // will be recomputed in useEffect below
      }
    } catch (e: any) {
      setTargetError(e?.response?.data?.detail || e.message || 'Failed to load Supabase table schema');
    } finally {
      setTargetSchemaLoading(false);
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

  const canRunOneToOne = Boolean(selectedSourceTable && selectedTargetTable);

  const renderOneToOneDialog = () => {
    if (!selectedSourceTable || !selectedTargetTable) return null;

    const sourceLabel = `${selectedSourceTable.schema}.${selectedSourceTable.name}`;
    const targetLabel = `${selectedTargetTable.schema}.${selectedTargetTable.name}`;

    return (
      <Dialog open={isConfirmOneToOneOpen} onOpenChange={setIsConfirmOneToOneOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Confirm 1:1 migration</DialogTitle>
            <DialogDescription>
              Migrate table 1:1 from <span className="font-mono">{sourceLabel}</span> (MSSQL) to{' '}
              <span className="font-mono">{targetLabel}</span> (Supabase).
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2 text-sm text-gray-700">
            <p>
              MSSQL will remain read-only. All writes will go to Supabase. Column names, types, nullability, and defaults
              will be used as-is where possible.
            </p>
            <p className="text-xs text-gray-600">
              Before running this in production, use the full mapping flow to review incompatible types and schema
              differences.
            </p>
          </div>
          <DialogFooter className="flex justify-end gap-2">
            <Button variant="outline" size="sm" onClick={() => setIsConfirmOneToOneOpen(false)}>
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={() => {
                // SCREEN 10 (stub): navigate to Migration Runner later
                // For now we just close the dialog; backend wiring will be added in Phase 7.
                setIsConfirmOneToOneOpen(false);
              }}
            >
              Continue to migration runner (stub)
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

  const showConnectionOverlay = !testOk && !schemaTree && !schemaLoading;

  return (
    <div className="space-y-4">
      {/* Keep the small MSSQL connection fields at the top */}
      <Card>
        <CardHeader>
          <CardTitle>Database Connection</CardTitle>
          <CardDescription>
            Connect to an external MSSQL database. Credentials are used only for this session and are never stored in
            Supabase.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
            <div className="space-y-1">
              <Label className="block text-xs font-medium text-gray-700">Host / IP</Label>
              <Input
                type="text"
                value={config.host}
                onChange={(e) => handleConfigChange('host', e.target.value)}
                placeholder="mssql.example.internal"
                className="h-8 text-sm"
              />
            </div>
            <div className="space-y-1">
              <Label className="block text-xs font-medium text-gray-700">Port</Label>
              <Input
                type="number"
                value={config.port}
                onChange={(e) => handleConfigChange('port', Number(e.target.value) || 1433)}
                placeholder="1433"
                className="h-8 text-sm"
              />
            </div>
            <div className="space-y-1">
              <Label className="block text-xs font-medium text-gray-700">Database</Label>
              <Input
                type="text"
                value={config.database}
                onChange={(e) => handleConfigChange('database', e.target.value)}
                placeholder="DB_A28F26_parts"
                className="h-8 text-sm"
              />
            </div>
            <div className="space-y-1">
              <Label className="block text-xs font-medium text-gray-700">Username</Label>
              <Input
                type="text"
                value={config.username}
                onChange={(e) => handleConfigChange('username', e.target.value)}
                placeholder="dbadmin"
                className="h-8 text-sm"
              />
            </div>
            <div className="space-y-1">
              <Label className="block text-xs font-medium text-gray-700">Password</Label>
              <Input
                type="password"
                value={config.password}
                onChange={(e) => handleConfigChange('password', e.target.value)}
                placeholder="••••••••"
                className="h-8 text-sm"
              />
            </div>
            <div className="flex items-center gap-2 mt-6">
              <input
                id="studio-encrypt"
                type="checkbox"
                className="h-4 w-4"
                checked={config.encrypt}
                onChange={(e) => handleConfigChange('encrypt', e.target.checked)}
              />
              <Label htmlFor="studio-encrypt" className="text-xs text-gray-700">
                Use SSL / Encrypt
              </Label>
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
      <Card className="max-w-6xl mx-auto">
        <CardHeader>
          <CardTitle className="text-base">Dual-DB Migration Studio</CardTitle>
          <CardDescription className="text-xs">
            MSSQL on the left, mapping actions in the middle, Supabase target on the right.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col md:flex-row gap-4">
            {/* LEFT: MSSQL source */}
            <div className="md:w-1/3 border rounded bg-white p-3 flex flex-col min-h-[320px] relative">
              <div className="flex items-center justify-between mb-2">
                <div>
                  <div className="font-semibold text-sm">MSSQL (legacy)</div>
                  <div className="text-[11px] text-gray-500">
                    {testOk ? 'Connected' : 'Not connected'}
                  </div>
                </div>
                {schemaLoading && <div className="text-[11px] text-gray-500">Loading schema...</div>}
              </div>
              <Input
                placeholder="Search tables..."
                value={schemaSearch}
                onChange={(e) => setSchemaSearch(e.target.value)}
                className="mb-2 h-8 text-sm"
              />
              {schemaError && <div className="mb-2 text-[11px] text-red-600">{schemaError}</div>}
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
                            selectedSourceTable?.schema === s.name && selectedSourceTable?.name === t.name;
                          return (
                            <div
                              key={t.name}
                              className={`cursor-pointer px-1 py-0.5 rounded border-b border-dotted border-gray-100 hover:bg-blue-50 ${
                                isSelected ? 'bg-blue-100 font-semibold' : ''
                              }`}
                              onClick={() => handleSelectSourceTable(s.name, t.name)}
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
              {showConnectionOverlay && (
                <div className="absolute inset-0 bg-white/70 flex flex-col items-center justify-center text-xs text-gray-600 gap-2">
                  {/* STATE 2a: No MSSQL connection / error overlay */}
                  <div className="font-medium">Connect to MSSQL first</div>
                  <Button size="sm" variant="outline" onClick={handleTestConnection} disabled={isTesting}>
                    {isTesting ? 'Testing...' : 'Test connection'}
                  </Button>
                </div>
              )}
            </div>

            {/* CENTER: Mapping summary & actions */}
            <div className="md:w-1/3 border rounded bg-white p-3 flex flex-col min-h-[320px]">
              <div className="flex items-center justify-between mb-2">
                <div className="font-semibold text-sm">Mapping / Actions</div>
              </div>
              <div className="flex gap-2 mb-3 flex-wrap">
                <Button
                  size="sm"
                  disabled={!canRunOneToOne}
                  onClick={() => {
                    if (!canRunOneToOne) return;
                    setIsConfirmOneToOneOpen(true);
                  }}
                >
                  Migrate 1:1 (structure + data)
                </Button>
                <Button size="sm" variant="outline" disabled={!selectedSourceTable || !selectedTargetTable}>
                  Configure mapping…
                </Button>
              </div>
              <div className="mb-2 text-xs text-gray-600 space-y-1">
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
                    <span className="text-gray-500">Select a table on the right</span>
                  )}
                </div>
              </div>

              <div className="flex-1 overflow-auto border rounded">
                <table className="min-w-full text-[11px]">
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
                        <td colSpan={5} className="px-2 py-4 text-center text-xs text-gray-500">
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
                            <span className="text-[11px] text-green-700 font-medium">auto mapped</span>
                          )}
                          {row.status === 'missing' && (
                            <span className="text-[11px] text-red-700 font-medium">missing</span>
                          )}
                          {row.status === 'needs-review' && (
                            <span className="text-[11px] text-yellow-700 font-medium">needs review</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="mt-2 flex gap-2 text-[11px] text-gray-500">
                <Button size="sm" variant="outline" disabled>
                  Compare schemas (stub)
                </Button>
                <span>Schema compare and full mapping screens will live here (Screens 3–4).</span>
              </div>
            </div>

            {/* RIGHT: Supabase target */}
            <div className="md:w-1/3 border rounded bg-white p-3 flex flex-col min-h-[320px]">
              <div className="flex items-center justify-between mb-2">
                <div className="font-semibold text-sm">Supabase (target)</div>
                {targetTablesLoading && <div className="text-[11px] text-gray-500">Loading tables...</div>}
              </div>
              <Input
                placeholder="Search tables..."
                value={targetSearch}
                onChange={(e) => setTargetSearch(e.target.value)}
                className="mb-2 h-8 text-sm"
              />
              {targetError && <div className="mb-2 text-[11px] text-red-600">{targetError}</div>}
              <div className="flex-1 overflow-auto border rounded">
                {filteredTargetTables.map((t) => {
                  const isSelected = selectedTargetTable?.schema === t.schema && selectedTargetTable?.name === t.name;
                  return (
                    <button
                      type="button"
                      key={`${t.schema}.${t.name}`}
                      className={`w-full text-left px-2 py-1 text-xs cursor-pointer border-b hover:bg-gray-50 ${
                        isSelected ? 'bg-blue-50 font-semibold' : ''
                      }`}
                      onClick={() => handleSelectTargetTable(t)}
                    >
                      <div className="font-mono text-[11px]">{t.name}</div>
                      {t.row_estimate != null && (
                        <div className="text-[10px] text-gray-500">~{Math.round(t.row_estimate)} rows</div>
                      )}
                    </button>
                  );
                })}
                {!targetTablesLoading && filteredTargetTables.length === 0 && (
                  <div className="px-2 py-3 text-[11px] text-gray-500 text-center">No tables found.</div>
                )}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {renderOneToOneDialog()}
    </div>
  );
};

export default AdminDataMigrationPage;
