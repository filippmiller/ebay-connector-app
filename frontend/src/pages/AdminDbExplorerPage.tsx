import React, { useEffect, useState } from 'react';
import FixedHeader from '@/components/FixedHeader';
import api from '@/lib/apiClient';

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

const AdminDbExplorerPage: React.FC = () => {
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

  useEffect(() => {
    const fetchTables = async () => {
      setLoadingTables(true);
      setError(null);
      try {
        const resp = await api.get<TableInfo[]>('/api/admin/db/tables');
        setTables(resp.data);
        setFilteredTables(resp.data);
      } catch (e: any) {
        console.error('Failed to load tables', e);
        setError(e?.response?.data?.detail || e.message || 'Failed to load tables');
      } finally {
        setLoadingTables(false);
      }
    };

    fetchTables();
  }, []);

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
      const resp = await api.get<TableSchemaResponse>(`/api/admin/db/tables/${encodeURIComponent(table.name)}/schema`);
      setSchema(resp.data);
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
      const resp = await api.get<RowsResponse>(`/api/admin/db/tables/${encodeURIComponent(table.name)}/rows`, {
        params: { limit, offset },
      });
      setRows(resp.data);
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
          <table className="min-w-full text-xs">
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
                    <td key={col} className="px-2 py-1 border whitespace-nowrap max-w-xs overflow-hidden text-ellipsis">
                      {row[col] === null || row[col] === undefined
                        ? ''
                        : typeof row[col] === 'object'
                        ? JSON.stringify(row[col])
                        : String(row[col])}
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
        <h1 className="text-2xl font-bold mb-4">Admin &rarr; DB Explorer</h1>
        {error && <div className="mb-3 text-sm text-red-600">{error}</div>}
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
                : `${filteredTables.length} tables in public schema`}
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
                  <div className="flex gap-2 text-sm">
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