import React, { useEffect, useState } from 'react';
import FixedHeader from '@/components/FixedHeader';
import api from '@/lib/apiClient';

type DbMode = 'supabase' | 'mssql';
interface TableInfo {
  schema: string;
  name: string;
  row_estimate: number | null;
}

interface ColumnInfo {
  name: string;
  data_type: string;
  is_nullable: boolean;
  is_primary_key: boolean;
  is_foreign_key: boolean;
  default: string | null;
}

interface TableSchemaResponse {
  schema: string;
  name: string;
  columns: ColumnInfo[];
}

interface RowsResponse {
  rows: Record<string, any>[];
  limit: number;
  offset: number;
  total_estimate: number | null;
}

interface GlobalSearchResultTable {
  schema: string;
  name: string;
  matched_columns: string[];
  rows: Record<string, any>[];
}

interface GlobalSearchResponse {
  query: string;
  tables: GlobalSearchResultTable[];
}

interface DuplicatesGroup {
  row_count: number;
  sample: Record<string, any>;
}

interface DuplicatesResponse {
  schema: string;
  name: string;
  total_duplicate_groups: number;
  groups: DuplicatesGroup[];
  delete_sql: string | null;
}

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

interface MssqlTablePreviewResponse {
  columns: string[];
  rows: any[][];
  limit: number;
  offset: number;
}

interface MssqlColumnInfo {
  name: string;
  dataType: string;
  isNullable: boolean;
  isPrimaryKey: boolean;
  defaultValue: string | null;
}

const AdminDbExplorerPage: React.FC = () => {
  const [activeDb, setActiveDb] = useState<DbMode>('supabase');
  const [tables, setTables] = useState<TableInfo[]>([]);
  const [filteredTables, setFilteredTables] = useState<TableInfo[]>([]);
  const [search, setSearch] = useState('');
  const [selectedTable, setSelectedTable] = useState<TableInfo | null>(null);
  const [schema, setSchema] = useState<TableSchemaResponse | null>(null);
  const [rows, setRows] = useState<RowsResponse | null>(null);
  const [activeTab, setActiveTab] = useState<'structure' | 'data'>('structure');
  const [rowsLimit, setRowsLimit] = useState(50);
  const [rowsOffset, setRowsOffset] = useState(0);
  const [loadingTables, setLoadingTables] = useState(false);
  const [loadingSchema, setLoadingSchema] = useState(false);
  const [loadingRows, setLoadingRows] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [globalSearchQuery, setGlobalSearchQuery] = useState('');
  const [globalSearchResult, setGlobalSearchResult] = useState<GlobalSearchResponse | null>(null);
  const [globalSearchLoading, setGlobalSearchLoading] = useState(false);
  const [duplicates, setDuplicates] = useState<DuplicatesResponse | null>(null);
  const [duplicatesLoading, setDuplicatesLoading] = useState(false);
  const [truncateLoading, setTruncateLoading] = useState(false);
  const [mssqlDatabase, setMssqlDatabase] = useState('');

  const buildMssqlConfig = (): MssqlConnectionConfig => ({
    host: '',
    port: 1433,
    database: mssqlDatabase,
    username: '',
    password: '',
    encrypt: true,
  });

  const fetchTables = async () => {
    setLoadingTables(true);
    setError(null);
    setSelectedTable(null);
    setSchema(null);
    setRows(null);
    setDuplicates(null);
    try {
      if (activeDb === 'supabase') {
        const resp = await api.get<TableInfo[]>('/api/admin/db/tables');
        setTables(resp.data);
        setFilteredTables(resp.data);
      } else {
        if (!mssqlDatabase.trim()) {
          setTables([]);
          setFilteredTables([]);
          return;
        }
        const resp = await api.post<MssqlSchemaTreeResponse>('/api/admin/mssql/schema-tree', buildMssqlConfig());
        const tree: MssqlSchemaTreeResponse = resp.data;
        const list: TableInfo[] = [];
        tree.schemas.forEach((s: { name: string; tables: { name: string }[] }) => {
          s.tables.forEach((t: { name: string }) => {
            list.push({ schema: s.name, name: t.name, row_estimate: null });
          });
        });
        setTables(list);
        setFilteredTables(list);
      }
    } catch (e: any) {
      console.error('Failed to load tables', e);
      setError(e?.response?.data?.detail || e.message || 'Failed to load tables');
      setTables([]);
      setFilteredTables([]);
    } finally {
      setLoadingTables(false);
    }
  };

  useEffect(() => {
    fetchTables();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeDb]);

  useEffect(() => {
    const q = search.trim().toLowerCase();
    if (!q) {
      setFilteredTables(tables);
    } else {
      setFilteredTables(
        tables.filter((t) => `${t.schema}.${t.name}`.toLowerCase().includes(q) || t.name.toLowerCase().includes(q))
      );
    }
  }, [search, tables]);

  const loadSchema = async (table: TableInfo) => {
    setLoadingSchema(true);
    setError(null);
    try {
      if (activeDb === 'supabase') {
        const resp = await api.get<TableSchemaResponse>(
          `/api/admin/db/tables/${encodeURIComponent(table.name)}/schema`,
        );
        setSchema(resp.data);
      } else {
        const resp = await api.post<MssqlColumnInfo[]>(
          '/api/admin/mssql/table-columns',
          {
            ...buildMssqlConfig(),
            schema: table.schema,
            table: table.name,
          },
        );
        const cols = resp.data;
        const mappedCols: ColumnInfo[] = cols.map((c) => ({
          name: c.name,
          data_type: c.dataType,
          is_nullable: c.isNullable,
          is_primary_key: c.isPrimaryKey,
          is_foreign_key: false,
          default: c.defaultValue,
        }));
        setSchema({ schema: table.schema, name: table.name, columns: mappedCols });
      }
    } catch (e: any) {
      console.error('Failed to load table schema', e);
      setError(e?.response?.data?.detail || e.message || 'Failed to load table schema');
      setSchema(null);
    } finally {
      setLoadingSchema(false);
    }
  };

  const loadRows = async (table: TableInfo, limit: number, offset: number) => {
    setLoadingRows(true);
    setError(null);
    try {
      if (activeDb === 'supabase') {
        const resp = await api.get<RowsResponse>(`/api/admin/db/tables/${encodeURIComponent(table.name)}/rows`, {
          params: { limit, offset },
        });
        setRows(resp.data);
      } else {
        const resp = await api.post<MssqlTablePreviewResponse>('/api/admin/mssql/table-preview', {
          ...buildMssqlConfig(),
          schema: table.schema,
          table: table.name,
          limit,
          offset,
        });
        const preview: MssqlTablePreviewResponse = resp.data;
        const cols = preview.columns;
        const rowObjects: Record<string, any>[] = preview.rows.map((row: any[]) => {
          const obj: Record<string, any> = {};
          cols.forEach((c: string, idx: number) => {
            obj[c] = row[idx];
          });
          return obj;
        });
        setRows({ rows: rowObjects, limit: preview.limit, offset: preview.offset, total_estimate: null });
      }
    } catch (e: any) {
      console.error('Failed to load table rows', e);
      setError(e?.response?.data?.detail || e.message || 'Failed to load table rows');
      setRows(null);
    } finally {
      setLoadingRows(false);
    }
  };

  const handleSelectTable = (table: TableInfo) => {
    setSelectedTable(table);
    setActiveTab('structure');
    setRows(null);
    setRowsOffset(0);
    setDuplicates(null);
    loadSchema(table);
  };

  const handleChangeTab = (tab: 'structure' | 'data') => {
    setActiveTab(tab);
    if (tab === 'data' && selectedTable && !rows) {
      loadRows(selectedTable, rowsLimit, rowsOffset);
    }
  };

  const handleChangeLimit = (newLimit: number) => {
    setRowsLimit(newLimit);
    setRowsOffset(0);
    if (selectedTable) {
      loadRows(selectedTable, newLimit, 0);
    }
  };

  const handleLoadMore = () => {
    if (!selectedTable || !rows) return;
    const newOffset = rowsOffset + rowsLimit;
    setRowsOffset(newOffset);
    loadRows(selectedTable, rowsLimit, newOffset);
  };

  const handleCheckDuplicates = async () => {
    if (!selectedTable) return;
    setDuplicatesLoading(true);
    setError(null);
    try {
      const resp = await api.get<DuplicatesResponse>(
        `/api/admin/db/tables/${encodeURIComponent(selectedTable.name)}/duplicates`,
        {
          params: { limit: 50 },
        }
      );
      setDuplicates(resp.data);
    } catch (e: any) {
      console.error('Failed to check duplicates', e);
      setError(e?.response?.data?.detail || e.message || 'Failed to check duplicates');
      setDuplicates(null);
    } finally {
      setDuplicatesLoading(false);
    }
  };

  const handleTruncateTable = async () => {
    if (!selectedTable) return;
    const confirm = window.confirm(
      `This will DELETE ALL ROWS from ${selectedTable.schema}.${selectedTable.name}. Are you sure?`
    );
    if (!confirm) return;
    setTruncateLoading(true);
    setError(null);
    try {
      await api.post(`/api/admin/db/tables/${encodeURIComponent(selectedTable.name)}/truncate`);
      // Clear local state and reload table metadata
      setRows(null);
      setSchema(null);
      setDuplicates(null);
      await loadSchema(selectedTable);
    } catch (e: any) {
      console.error('Failed to truncate table', e);
      setError(e?.response?.data?.detail || e.message || 'Failed to clear table data');
    } finally {
      setTruncateLoading(false);
    }
  };

  const renderStructure = () => {
    if (loadingSchema) {
      return <div className="text-sm text-gray-500">Loading structure...</div>;
    }
    if (!schema) {
      return <div className="text-sm text-gray-500">No structure loaded.</div>;
    }
    return (
      <table className="min-w-full border text-sm">
        <thead className="bg-gray-100">
          <tr>
            <th className="px-2 py-1 border">Column</th>
            <th className="px-2 py-1 border">Type</th>
            <th className="px-2 py-1 border">Nullable</th>
            <th className="px-2 py-1 border">PK</th>
            <th className="px-2 py-1 border">FK</th>
            <th className="px-2 py-1 border">Default</th>
          </tr>
        </thead>
        <tbody>
          {schema.columns.map((col) => (
            <tr key={col.name}>
              <td className="px-2 py-1 border font-mono text-xs">{col.name}</td>
              <td className="px-2 py-1 border text-xs">{col.data_type}</td>
              <td className="px-2 py-1 border text-xs">{col.is_nullable ? 'YES' : 'NO'}</td>
              <td className="px-2 py-1 border text-xs">{col.is_primary_key ? 'YES' : ''}</td>
              <td className="px-2 py-1 border text-xs">{col.is_foreign_key ? 'YES' : ''}</td>
              <td className="px-2 py-1 border text-xs max-w-xs truncate" title={col.default || undefined}>
                {col.default}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  };

  const renderData = () => {
    if (loadingRows) {
      return <div className="text-sm text-gray-500">Loading rows...</div>;
    }
    if (!rows || !rows.rows.length) {
      return <div className="text-sm text-gray-500">No rows to display.</div>;
    }

    const columns = Array.from(
      rows.rows.reduce<Set<string>>((acc, row) => {
        Object.keys(row).forEach((k) => acc.add(k));
        return acc;
      }, new Set())
    );

    return (
      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs text-gray-600">
          <div>
            Rows {rowsOffset + 1}–{rowsOffset + rows.rows.length} (limit {rowsLimit}
            {rows.total_estimate != null && `, estimate ~${Math.round(rows.total_estimate)}`} )
          </div>
          <div className="flex items-center gap-2">
            <span>Limit:</span>
            <select
              className="border rounded px-1 py-0.5 text-xs"
              value={rowsLimit}
              onChange={(e) => handleChangeLimit(Number(e.target.value) || 50)}
            >
              <option value={20}>20</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
              <option value={200}>200</option>
            </select>
          </div>
        </div>
        <div className="overflow-auto border rounded max-h-[60vh]">
          <table className="min-w-full text-xs table-fixed">
            <thead className="bg-gray-100">
              <tr>
                {columns.map((col) => (
                  <th key={col} className="px-2 py-1 border text-left font-mono text-[11px]">
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.rows.map((row, idx) => (
                <tr key={idx} className="border-t">
                  {columns.map((col) => (
                    <td
                      key={col}
                      className="px-2 py-1 border whitespace-nowrap max-w-xs overflow-x-auto text-[11px] font-mono"
                    >
                      <div className="inline-block whitespace-pre select-text">
                        {row[col] === null || row[col] === undefined
                          ? ''
                          : typeof row[col] === 'object'
                          ? JSON.stringify(row[col], null, 2)
                          : String(row[col])}
                      </div>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="flex justify-end mt-2">
          <button
            className="px-3 py-1 border rounded text-xs bg-gray-50 hover:bg-gray-100"
            onClick={handleLoadMore}
          >
            Load more
          </button>
        </div>
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <FixedHeader />
      <div className="pt-12 p-4">
        <h1 className="text-2xl font-bold mb-2">Admin &rarr; DB Explorer</h1>
        <div className="mb-3 flex items-center justify-between">
          <div className="flex gap-2 text-sm">
            <button
              className={`px-3 py-1 rounded border text-xs ${
                activeDb === 'supabase' ? 'bg-blue-600 text-white' : 'bg-white text-gray-700'
              }`}
              onClick={() => setActiveDb('supabase')}
            >
              Supabase (Postgres)
            </button>
            <button
              className={`px-3 py-1 rounded border text-xs ${
                activeDb === 'mssql' ? 'bg-blue-600 text-white' : 'bg-white text-gray-700'
              }`}
              onClick={() => setActiveDb('mssql')}
            >
              MSSQL (legacy)
            </button>
          </div>
          {activeDb === 'mssql' && (
            <div className="flex items-center gap-2 text-xs">
              <span>MSSQL database:</span>
              <input
                type="text"
                className="border rounded px-2 py-1 text-xs"
                placeholder="DB_A28F26_parts"
                value={mssqlDatabase}
                onChange={(e) => setMssqlDatabase(e.target.value)}
              />
              <button
                className="px-3 py-1 border rounded text-xs bg-white hover:bg-gray-50"
                onClick={fetchTables}
              >
                Load tables
              </button>
            </div>
          )}
        </div>
        {error && <div className="mb-3 text-sm text-red-600">{error}</div>}
        <div className="mb-3 flex items-center gap-2">
          <input
            type="text"
            className="flex-1 border rounded px-2 py-1 text-sm"
            placeholder={
              activeDb === 'supabase'
                ? 'Global search (substring, case-insensitive) across text columns in public schema...'
                : 'Global search (substring, case-insensitive) across text columns in MSSQL database...'
            }
            value={globalSearchQuery}
            onChange={(e) => setGlobalSearchQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && globalSearchQuery.trim()) {
                const run = async () => {
                  try {
                    setGlobalSearchLoading(true);
                    setGlobalSearchResult(null);
                    let resp;
                    if (activeDb === 'supabase') {
                      resp = await api.get<GlobalSearchResponse>('/api/admin/db/search', {
                        params: { q: globalSearchQuery.trim(), limit: 20 },
                      });
                    } else {
                      if (!mssqlDatabase.trim()) {
                        setError('Enter MSSQL database name before running search');
                        return;
                      }
                      resp = await api.post<GlobalSearchResponse>('/api/admin/mssql/search', {
                        ...buildMssqlConfig(),
                        q: globalSearchQuery.trim(),
                        limit: 20,
                      });
                    }
                    setGlobalSearchResult(resp.data);
                  } catch (err: any) {
                    console.error('Global search failed', err);
                    setError(err?.response?.data?.detail || err.message || 'Global search failed');
                  } finally {
                    setGlobalSearchLoading(false);
                  }
                };
                void run();
              }
            }}
          />
          <button
            className="px-3 py-1 border rounded text-sm bg-white hover:bg-gray-50"
            disabled={globalSearchLoading || !globalSearchQuery.trim()}
            onClick={() => {
              if (!globalSearchQuery.trim()) return;
              const run = async () => {
                try {
                  setGlobalSearchLoading(true);
                  setGlobalSearchResult(null);
                  let resp;
                  if (activeDb === 'supabase') {
                    resp = await api.get<GlobalSearchResponse>('/api/admin/db/search', {
                      params: { q: globalSearchQuery.trim(), limit: 20 },
                    });
                  } else {
                    if (!mssqlDatabase.trim()) {
                      setError('Enter MSSQL database name before running search');
                      return;
                    }
                    resp = await api.post<GlobalSearchResponse>('/api/admin/mssql/search', {
                      ...buildMssqlConfig(),
                      q: globalSearchQuery.trim(),
                      limit: 20,
                    });
                  }
                  setGlobalSearchResult(resp.data);
                } catch (err: any) {
                  console.error('Global search failed', err);
                  setError(err?.response?.data?.detail || err.message || 'Global search failed');
                } finally {
                  setGlobalSearchLoading(false);
                }
              };
              void run();
            }}
          >
            {globalSearchLoading ? 'Searching...' : 'Search all tables'}
          </button>
        </div>
        {globalSearchResult && (
          <div className="mb-4 border rounded bg-white p-3 text-xs max-h-[40vh] overflow-auto">
            <div className="mb-2 font-semibold">Global search results for "{globalSearchResult.query}"</div>
            {globalSearchResult.tables.length === 0 ? (
              <div className="text-gray-500">No matches found in text columns.</div>
            ) : (
              <div className="space-y-3">
                {globalSearchResult.tables.map((t) => (
                  <div key={`${t.schema}.${t.name}`}>
                    <div className="font-mono text-[11px] mb-1">
                      {t.schema}.{t.name} (columns: {t.matched_columns.join(', ')})
                    </div>
                    <div className="overflow-auto border rounded max-h-40">
                      <table className="min-w-full text-[11px] table-fixed">
                        <thead className="bg-gray-100">
                          <tr>
                            {Object.keys(t.rows[0] || {}).map((col) => (
                              <th key={col} className="px-2 py-1 border font-mono text-[11px]">
                                {col}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {t.rows.map((row, idx) => (
                            <tr key={idx} className="border-t">
                              {Object.keys(t.rows[0] || {}).map((col) => (
                                <td
                                  key={col}
                                  className="px-2 py-1 border whitespace-nowrap max-w-xs overflow-x-auto text-[11px] font-mono"
                                >
                                  <div className="inline-block whitespace-pre select-text">
                                    {row[col] === null || row[col] === undefined
                                      ? ''
                                      : typeof row[col] === 'object'
                                      ? JSON.stringify(row[col], null, 2)
                                      : String(row[col])}
                                  </div>
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
        <div className="grid grid-cols-12 gap-4">
          <div className="col-span-3 border rounded bg-white p-3 flex flex-col">
            <div className="mb-2">
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Filter tables..."
                className="w-full border rounded px-2 py-1 text-sm"
              />
            </div>
            <div className="text-xs text-gray-500 mb-1">
              {loadingTables
                ? 'Loading tables...'
                : activeDb === 'supabase'
                ? `${filteredTables.length} tables in public schema`
                : `${filteredTables.length} tables in MSSQL database`}
            </div>
            <div className="flex-1 overflow-auto border rounded">
              {filteredTables.map((t) => {
                const isSelected = selectedTable?.schema === t.schema && selectedTable?.name === t.name;
                return (
                  <div
                    key={`${t.schema}.${t.name}`}
                    className={`px-2 py-1 text-sm cursor-pointer border-b hover:bg-gray-100 ${
                      isSelected ? 'bg-blue-50 font-semibold' : ''
                    }`}
                    onClick={() => handleSelectTable(t)}
                  >
                    <div className="font-mono text-xs">{t.name}</div>
                    {t.row_estimate != null && (
                      <div className="text-[10px] text-gray-500">~{Math.round(t.row_estimate)} rows</div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          <div className="col-span-9 border rounded bg-white p-3 min-h-[400px]">
            {!selectedTable ? (
              <div className="h-full flex items-center justify-center text-sm text-gray-500">
                Select a table to see its structure and data.
              </div>
            ) : (
              <div className="flex flex-col h-full">
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <div className="font-mono text-sm">
                      {selectedTable.schema}.{selectedTable.name}
                    </div>
                    {selectedTable.row_estimate != null && (
                      <div className="text-xs text-gray-500">
                        Estimated rows: ~{Math.round(selectedTable.row_estimate)}
                      </div>
                    )}
                  </div>
                  <div className="flex items-center gap-2 text-sm">
                    {activeDb === 'supabase' && (
                      <>
                        <button
                          className="px-3 py-1 rounded border text-xs bg-white hover:bg-gray-50"
                          onClick={handleCheckDuplicates}
                          disabled={duplicatesLoading}
                        >
                          {duplicatesLoading ? 'Checking duplicates...' : 'Check duplicates'}
                        </button>
                        <button
                          className="px-3 py-1 rounded border text-xs bg-white hover:bg-red-50 text-red-700 border-red-300"
                          onClick={handleTruncateTable}
                          disabled={truncateLoading}
                        >
                          {truncateLoading ? 'Clearing...' : 'Clear table data'}
                        </button>
                      </>
                    )}
                    <button
                      className={`px-3 py-1 rounded border text-xs ${
                        activeTab === 'structure' ? 'bg-blue-600 text-white' : 'bg-white text-gray-700'
                      }`}
                      onClick={() => handleChangeTab('structure')}
                    >
                      Structure
                    </button>
                    <button
                      className={`px-3 py-1 rounded border text-xs ${
                        activeTab === 'data' ? 'bg-blue-600 text-white' : 'bg-white text-gray-700'
                      }`}
                      onClick={() => handleChangeTab('data')}
                    >
                      Data
                    </button>
                  </div>
                </div>

                {activeDb === 'supabase' && duplicates && (
                  <div className="mt-3 mb-2 border rounded bg-yellow-50 p-2 text-xs max-h-64 overflow-auto">
                    <div className="font-semibold mb-1">Duplicate groups</div>
                    {duplicates.total_duplicate_groups === 0 ? (
                      <div className="text-gray-600">No duplicates found (grouping by all columns).</div>
                    ) : (
                      <>
                        <div className="mb-2 text-gray-700">
                          Found {duplicates.total_duplicate_groups} duplicate group(s). Below is a sample and a
                          suggested SQL snippet you can run (carefully!) to delete duplicates while keeping one row per
                          group.
                        </div>
                        <div className="space-y-2 mb-2">
                          {duplicates.groups.map((g, idx) => (
                            <div key={idx} className="border rounded bg-white p-2">
                              <div className="mb-1 font-mono">Row count in group: {g.row_count}</div>
                              <pre className="text-[11px] whitespace-pre-wrap break-all bg-gray-50 p-1 rounded">
                                {JSON.stringify(g.sample, null, 2)}
                              </pre>
                            </div>
                          ))}
                        </div>
                        {duplicates.delete_sql && (
                          <div className="mt-2">
                            <div className="mb-1 font-semibold">Suggested DELETE SQL</div>
                            <pre className="text-[11px] whitespace-pre-wrap break-all bg-gray-100 p-2 rounded">
                              {duplicates.delete_sql}
                            </pre>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                )}

                <div className="flex-1 overflow-auto mt-2">
                  {activeTab === 'structure' ? renderStructure() : renderData()}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default AdminDbExplorerPage;