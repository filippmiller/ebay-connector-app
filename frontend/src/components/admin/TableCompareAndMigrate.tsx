/**
 * TableCompareAndMigrate Component
 * 
 * Provides UI for:
 * 1. Comparing schema and data between two tables (MSSQL/Supabase)
 * 2. Identifying missing rows and schema differences
 * 3. Safely migrating missing data from Source → Target
 */

import React, { useState } from 'react';
import api from '@/lib/apiClient';

// =============================================================================
// Types
// =============================================================================

type DbType = 'mssql' | 'supabase';

interface DbEndpoint {
    db: DbType;
    database?: string;
    schema_name?: string;
    table: string;
}

interface TableOption {
    schema: string;
    name: string;
    row_estimate: number | null;
}

interface ColumnInfo {
    name: string;
    data_type: string;
    normalized_type: string;
    is_nullable: boolean;
    is_primary_key: boolean;
    default_value: string | null;
}

interface TypeMismatch {
    column: string;
    source_type: string;
    target_type: string;
    source_normalized: string;
    target_normalized: string;
}

interface SchemaCompareResponse {
    source_column_count: number;
    target_column_count: number;
    source_columns: ColumnInfo[];
    target_columns: ColumnInfo[];
    common_columns: string[];
    missing_in_target_columns: string[];
    extra_in_target_columns: string[];
    type_mismatch_columns: TypeMismatch[];
    auto_detected_key: string | null;
    key_detection_warning: string | null;
}

interface KeyRange {
    start: number;
    end: number;
    count: number;
}

interface DataSummaryResponse {
    source_row_count: number;
    target_row_count: number;
    source_key_min: number | null;
    source_key_max: number | null;
    target_key_min: number | null;
    target_key_max: number | null;
    keys_only_in_source_count: number;
    keys_only_in_target_count: number;
    keys_in_both_count: number;
    missing_in_target_ranges: KeyRange[];
    missing_in_source_ranges: KeyRange[];
    truncated: boolean;
    truncated_message: string | null;
}

interface MigrateResponse {
    dry_run: boolean;
    planned_inserts_count?: number;
    columns_to_insert?: string[];
    potential_issues?: string[];
    inserted_count?: number;
    skipped_conflicts_count?: number;
    errors_count?: number;
    migration_log_id?: number;
    batch_logs?: string[];
}

interface Props {
    mssqlDatabase: string;
    supabaseTables: TableOption[];
    mssqlTables: TableOption[];
    onRefreshTables?: () => void;
}

// =============================================================================
// Component
// =============================================================================

const TableCompareAndMigrate: React.FC<Props> = ({
    mssqlDatabase,
    supabaseTables,
    mssqlTables,
    onRefreshTables,
}) => {
    // Source/Target selection
    const [sourceDb, setSourceDb] = useState<DbType>('mssql');
    const [sourceTable, setSourceTable] = useState<string>('');
    const [sourceSchema, setSourceSchema] = useState<string>('dbo');
    const [targetDb, setTargetDb] = useState<DbType>('supabase');
    const [targetTable, setTargetTable] = useState<string>('');
    const [targetSchema, setTargetSchema] = useState<string>('public');

    // Key column
    const [keyColumn, setKeyColumn] = useState<string>('');
    const [availableKeyColumns, setAvailableKeyColumns] = useState<string[]>([]);

    // Compare results
    const [schemaResult, setSchemaResult] = useState<SchemaCompareResponse | null>(null);
    const [dataSummary, setDataSummary] = useState<DataSummaryResponse | null>(null);

    // Migration
    const [selectedRanges, setSelectedRanges] = useState<KeyRange[]>([]);
    const [migrateResult, setMigrateResult] = useState<MigrateResponse | null>(null);

    // UI state
    const [activePanel, setActivePanel] = useState<'schema' | 'data' | 'migrate'>('schema');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Get table list based on selected DB
    const getTablesFor = (db: DbType) => {
        return db === 'mssql' ? mssqlTables : supabaseTables;
    };

    // Build endpoint object
    const buildEndpoint = (db: DbType, schema: string, table: string): DbEndpoint => ({
        db,
        database: db === 'mssql' ? mssqlDatabase : undefined,
        schema_name: schema,
        table,
    });

    // =============================================================================
    // Compare Schema
    // =============================================================================

    const handleCompareSchema = async () => {
        if (!sourceTable || !targetTable) {
            setError('Please select both source and target tables');
            return;
        }

        setLoading(true);
        setError(null);
        setSchemaResult(null);
        setDataSummary(null);
        setMigrateResult(null);

        try {
            const response = await api.post<SchemaCompareResponse>('/api/db-compare/schema', {
                source: buildEndpoint(sourceDb, sourceSchema, sourceTable),
                target: buildEndpoint(targetDb, targetSchema, targetTable),
            });

            setSchemaResult(response.data);

            // Set auto-detected key if available
            if (response.data.auto_detected_key) {
                setKeyColumn(response.data.auto_detected_key);
            }

            // Set available key columns (common columns)
            setAvailableKeyColumns(response.data.common_columns);

            setActivePanel('schema');
        } catch (e: any) {
            setError(e?.response?.data?.detail || e.message || 'Failed to compare schema');
        } finally {
            setLoading(false);
        }
    };

    // =============================================================================
    // Compare Data
    // =============================================================================

    const handleCompareData = async () => {
        if (!sourceTable || !targetTable || !keyColumn) {
            setError('Please select source, target tables and key column');
            return;
        }

        setLoading(true);
        setError(null);
        setDataSummary(null);

        try {
            const response = await api.post<DataSummaryResponse>('/api/db-compare/data-summary', {
                source: buildEndpoint(sourceDb, sourceSchema, sourceTable),
                target: buildEndpoint(targetDb, targetSchema, targetTable),
                key_column: keyColumn,
            });

            setDataSummary(response.data);

            // Pre-select all missing ranges for migration
            setSelectedRanges(response.data.missing_in_target_ranges);

            setActivePanel('data');
        } catch (e: any) {
            setError(e?.response?.data?.detail || e.message || 'Failed to compare data');
        } finally {
            setLoading(false);
        }
    };

    // =============================================================================
    // Migration
    // =============================================================================

    const handleMigrate = async (dryRun: boolean) => {
        if (!sourceTable || !targetTable || !keyColumn) {
            setError('Please complete comparison first');
            return;
        }

        if (selectedRanges.length === 0) {
            setError('No ranges selected for migration');
            return;
        }

        setLoading(true);
        setError(null);
        setMigrateResult(null);

        try {
            const response = await api.post<MigrateResponse>('/api/db-compare/migrate', {
                source: buildEndpoint(sourceDb, sourceSchema, sourceTable),
                target: buildEndpoint(targetDb, targetSchema, targetTable),
                key_column: keyColumn,
                mode: 'INSERT_MISSING_ONLY',
                ranges: selectedRanges,
                dry_run: dryRun,
            });

            setMigrateResult(response.data);
            setActivePanel('migrate');

            // If real migration completed, suggest refresh
            if (!dryRun && response.data.inserted_count && response.data.inserted_count > 0) {
                onRefreshTables?.();
            }
        } catch (e: any) {
            setError(e?.response?.data?.detail || e.message || 'Migration failed');
        } finally {
            setLoading(false);
        }
    };

    // Toggle range selection
    const toggleRange = (range: KeyRange) => {
        const exists = selectedRanges.some(r => r.start === range.start && r.end === range.end);
        if (exists) {
            setSelectedRanges(selectedRanges.filter(r => !(r.start === range.start && r.end === range.end)));
        } else {
            setSelectedRanges([...selectedRanges, range]);
        }
    };

    // =============================================================================
    // Render
    // =============================================================================

    return (
        <div className="space-y-4">
            {/* Header */}
            <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold">Table Compare & Migrate</h2>
                <div className="text-xs text-gray-500">
                    Compare tables across MSSQL and Supabase, then safely migrate missing data
                </div>
            </div>

            {/* Source/Target Selection */}
            <div className="grid grid-cols-2 gap-4 p-4 bg-gray-50 rounded border">
                {/* Source */}
                <div className="space-y-2">
                    <div className="font-medium text-sm text-green-700">📤 Source (read-only)</div>
                    <div className="flex gap-2">
                        <select
                            className="border rounded px-2 py-1 text-xs"
                            value={sourceDb}
                            onChange={(e) => {
                                setSourceDb(e.target.value as DbType);
                                setSourceTable('');
                                setSourceSchema(e.target.value === 'mssql' ? 'dbo' : 'public');
                            }}
                        >
                            <option value="mssql">MSSQL (Legacy)</option>
                            <option value="supabase">Supabase (Postgres)</option>
                        </select>
                        <select
                            className="border rounded px-2 py-1 text-xs flex-1"
                            value={sourceTable}
                            onChange={(e) => setSourceTable(e.target.value)}
                        >
                            <option value="">-- Select table --</option>
                            {getTablesFor(sourceDb).map((t) => (
                                <option key={`${t.schema}.${t.name}`} value={t.name}>
                                    {t.name} {t.row_estimate != null && `(~${t.row_estimate.toLocaleString()})`}
                                </option>
                            ))}
                        </select>
                    </div>
                    <input
                        type="text"
                        className="border rounded px-2 py-1 text-xs w-full"
                        placeholder="Schema (e.g., dbo)"
                        value={sourceSchema}
                        onChange={(e) => setSourceSchema(e.target.value)}
                    />
                </div>

                {/* Target */}
                <div className="space-y-2">
                    <div className="font-medium text-sm text-blue-700">📥 Target (insert only)</div>
                    <div className="flex gap-2">
                        <select
                            className="border rounded px-2 py-1 text-xs"
                            value={targetDb}
                            onChange={(e) => {
                                setTargetDb(e.target.value as DbType);
                                setTargetTable('');
                                setTargetSchema(e.target.value === 'mssql' ? 'dbo' : 'public');
                            }}
                        >
                            <option value="supabase">Supabase (Postgres)</option>
                            <option value="mssql">MSSQL (Legacy)</option>
                        </select>
                        <select
                            className="border rounded px-2 py-1 text-xs flex-1"
                            value={targetTable}
                            onChange={(e) => setTargetTable(e.target.value)}
                        >
                            <option value="">-- Select table --</option>
                            {getTablesFor(targetDb).map((t) => (
                                <option key={`${t.schema}.${t.name}`} value={t.name}>
                                    {t.name} {t.row_estimate != null && `(~${t.row_estimate.toLocaleString()})`}
                                </option>
                            ))}
                        </select>
                    </div>
                    <input
                        type="text"
                        className="border rounded px-2 py-1 text-xs w-full"
                        placeholder="Schema (e.g., public)"
                        value={targetSchema}
                        onChange={(e) => setTargetSchema(e.target.value)}
                    />
                </div>
            </div>

            {/* Actions */}
            <div className="flex items-center gap-2">
                <button
                    className="px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:opacity-50"
                    onClick={handleCompareSchema}
                    disabled={loading || !sourceTable || !targetTable}
                >
                    {loading ? 'Comparing...' : '1. Compare Schema'}
                </button>

                {schemaResult && (
                    <>
                        <select
                            className="border rounded px-2 py-1 text-xs"
                            value={keyColumn}
                            onChange={(e) => setKeyColumn(e.target.value)}
                        >
                            <option value="">-- Select key column --</option>
                            {availableKeyColumns.map((col) => (
                                <option key={col} value={col}>
                                    {col}
                                </option>
                            ))}
                        </select>

                        <button
                            className="px-4 py-2 bg-green-600 text-white rounded text-sm hover:bg-green-700 disabled:opacity-50"
                            onClick={handleCompareData}
                            disabled={loading || !keyColumn}
                        >
                            {loading ? 'Comparing...' : '2. Compare Data'}
                        </button>
                    </>
                )}
            </div>

            {/* Error Display */}
            {error && (
                <div className="p-3 bg-red-50 border border-red-200 rounded text-red-700 text-sm">
                    {error}
                </div>
            )}

            {/* Key Detection Warning */}
            {schemaResult?.key_detection_warning && (
                <div className="p-3 bg-yellow-50 border border-yellow-200 rounded text-yellow-700 text-sm">
                    ⚠️ {schemaResult.key_detection_warning}
                </div>
            )}

            {/* Tabs */}
            {(schemaResult || dataSummary) && (
                <div className="border-b flex gap-1">
                    <button
                        className={`px-4 py-2 text-sm border-b-2 ${activePanel === 'schema' ? 'border-blue-600 text-blue-600' : 'border-transparent'}`}
                        onClick={() => setActivePanel('schema')}
                    >
                        Schema Diff
                    </button>
                    {dataSummary && (
                        <>
                            <button
                                className={`px-4 py-2 text-sm border-b-2 ${activePanel === 'data' ? 'border-blue-600 text-blue-600' : 'border-transparent'}`}
                                onClick={() => setActivePanel('data')}
                            >
                                Data Diff
                            </button>
                            <button
                                className={`px-4 py-2 text-sm border-b-2 ${activePanel === 'migrate' ? 'border-blue-600 text-blue-600' : 'border-transparent'}`}
                                onClick={() => setActivePanel('migrate')}
                            >
                                Migration
                            </button>
                        </>
                    )}
                </div>
            )}

            {/* Schema Diff Panel */}
            {activePanel === 'schema' && schemaResult && (
                <div className="space-y-4">
                    {/* Summary */}
                    <div className="grid grid-cols-4 gap-4 text-center">
                        <div className="p-3 bg-gray-100 rounded">
                            <div className="text-2xl font-bold">{schemaResult.source_column_count}</div>
                            <div className="text-xs text-gray-600">Source columns</div>
                        </div>
                        <div className="p-3 bg-gray-100 rounded">
                            <div className="text-2xl font-bold">{schemaResult.target_column_count}</div>
                            <div className="text-xs text-gray-600">Target columns</div>
                        </div>
                        <div className="p-3 bg-green-100 rounded">
                            <div className="text-2xl font-bold text-green-700">{schemaResult.common_columns.length}</div>
                            <div className="text-xs text-green-600">Common columns</div>
                        </div>
                        <div className="p-3 bg-yellow-100 rounded">
                            <div className="text-2xl font-bold text-yellow-700">{schemaResult.type_mismatch_columns.length}</div>
                            <div className="text-xs text-yellow-600">Type mismatches</div>
                        </div>
                    </div>

                    {/* Missing in Target */}
                    {schemaResult.missing_in_target_columns.length > 0 && (
                        <div className="p-3 bg-orange-50 border border-orange-200 rounded">
                            <div className="font-medium text-orange-700 mb-2">
                                ⚠️ Columns missing in Target ({schemaResult.missing_in_target_columns.length})
                            </div>
                            <div className="text-xs text-orange-600 flex flex-wrap gap-1">
                                {schemaResult.missing_in_target_columns.map((col) => (
                                    <span key={col} className="px-2 py-0.5 bg-orange-100 rounded">{col}</span>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Extra in Target */}
                    {schemaResult.extra_in_target_columns.length > 0 && (
                        <div className="p-3 bg-blue-50 border border-blue-200 rounded">
                            <div className="font-medium text-blue-700 mb-2">
                                ℹ️ Extra columns in Target ({schemaResult.extra_in_target_columns.length})
                            </div>
                            <div className="text-xs text-blue-600 flex flex-wrap gap-1">
                                {schemaResult.extra_in_target_columns.map((col) => (
                                    <span key={col} className="px-2 py-0.5 bg-blue-100 rounded">{col}</span>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Type Mismatches */}
                    {schemaResult.type_mismatch_columns.length > 0 && (
                        <div className="p-3 bg-yellow-50 border border-yellow-200 rounded">
                            <div className="font-medium text-yellow-700 mb-2">
                                ⚠️ Type mismatches ({schemaResult.type_mismatch_columns.length})
                            </div>
                            <table className="w-full text-xs">
                                <thead>
                                    <tr className="text-left">
                                        <th className="pb-1">Column</th>
                                        <th className="pb-1">Source Type</th>
                                        <th className="pb-1">Target Type</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {schemaResult.type_mismatch_columns.map((m) => (
                                        <tr key={m.column}>
                                            <td className="py-0.5 font-mono">{m.column}</td>
                                            <td className="py-0.5">{m.source_type} ({m.source_normalized})</td>
                                            <td className="py-0.5">{m.target_type} ({m.target_normalized})</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>
            )}

            {/* Data Diff Panel */}
            {activePanel === 'data' && dataSummary && (
                <div className="space-y-4">
                    {/* Summary */}
                    <div className="grid grid-cols-3 gap-4 text-center">
                        <div className="p-3 bg-gray-100 rounded">
                            <div className="text-2xl font-bold">{dataSummary.source_row_count.toLocaleString()}</div>
                            <div className="text-xs text-gray-600">Source rows</div>
                            <div className="text-xs text-gray-400">
                                Keys: {dataSummary.source_key_min?.toLocaleString()} – {dataSummary.source_key_max?.toLocaleString()}
                            </div>
                        </div>
                        <div className="p-3 bg-gray-100 rounded">
                            <div className="text-2xl font-bold">{dataSummary.target_row_count.toLocaleString()}</div>
                            <div className="text-xs text-gray-600">Target rows</div>
                            <div className="text-xs text-gray-400">
                                Keys: {dataSummary.target_key_min?.toLocaleString()} – {dataSummary.target_key_max?.toLocaleString()}
                            </div>
                        </div>
                        <div className="p-3 bg-green-100 rounded">
                            <div className="text-2xl font-bold text-green-700">{dataSummary.keys_in_both_count.toLocaleString()}</div>
                            <div className="text-xs text-green-600">Keys in both</div>
                        </div>
                    </div>

                    {/* Missing in Target */}
                    {dataSummary.keys_only_in_source_count > 0 && (
                        <div className="p-3 bg-orange-50 border border-orange-200 rounded">
                            <div className="font-medium text-orange-700 mb-2">
                                📤 Missing in Target: {dataSummary.keys_only_in_source_count.toLocaleString()} keys
                            </div>
                            <div className="space-y-1">
                                {dataSummary.missing_in_target_ranges.map((range, idx) => (
                                    <div
                                        key={idx}
                                        className={`text-xs p-2 rounded cursor-pointer flex justify-between items-center ${selectedRanges.some(r => r.start === range.start && r.end === range.end)
                                            ? 'bg-orange-200 border border-orange-400'
                                            : 'bg-orange-100 hover:bg-orange-200'
                                            }`}
                                        onClick={() => toggleRange(range)}
                                    >
                                        <span>
                                            <input
                                                type="checkbox"
                                                checked={selectedRanges.some(r => r.start === range.start && r.end === range.end)}
                                                onChange={() => toggleRange(range)}
                                                className="mr-2"
                                            />
                                            Range: {range.start.toLocaleString()} – {range.end.toLocaleString()}
                                        </span>
                                        <span className="font-medium">{range.count.toLocaleString()} rows</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Missing in Source */}
                    {dataSummary.keys_only_in_target_count > 0 && (
                        <div className="p-3 bg-blue-50 border border-blue-200 rounded">
                            <div className="font-medium text-blue-700 mb-2">
                                📥 Extra in Target: {dataSummary.keys_only_in_target_count.toLocaleString()} keys
                            </div>
                            <div className="text-xs text-blue-600">
                                These keys exist in Target but not in Source. No action needed.
                            </div>
                        </div>
                    )}

                    {/* Truncation warning */}
                    {dataSummary.truncated && (
                        <div className="p-3 bg-yellow-50 border border-yellow-200 rounded text-yellow-700 text-sm">
                            ⚠️ {dataSummary.truncated_message}
                        </div>
                    )}
                </div>
            )}

            {/* Migration Panel */}
            {activePanel === 'migrate' && dataSummary && (
                <div className="space-y-4">
                    {/* Selection Summary */}
                    <div className="p-3 bg-gray-100 rounded">
                        <div className="font-medium mb-2">Selected for Migration</div>
                        <div className="text-sm">
                            {selectedRanges.length === 0 ? (
                                <span className="text-gray-500">No ranges selected</span>
                            ) : (
                                <>
                                    {selectedRanges.length} range(s), {selectedRanges.reduce((sum, r) => sum + r.count, 0).toLocaleString()} total rows
                                </>
                            )}
                        </div>
                    </div>

                    {/* Migration Actions */}
                    <div className="flex gap-2">
                        <button
                            className="px-4 py-2 bg-yellow-600 text-white rounded text-sm hover:bg-yellow-700 disabled:opacity-50"
                            onClick={() => handleMigrate(true)}
                            disabled={loading || selectedRanges.length === 0}
                        >
                            {loading ? 'Processing...' : '🔍 Dry Run (Preview)'}
                        </button>
                        <button
                            className="px-4 py-2 bg-green-600 text-white rounded text-sm hover:bg-green-700 disabled:opacity-50"
                            onClick={() => handleMigrate(false)}
                            disabled={loading || selectedRanges.length === 0 || !migrateResult || migrateResult.dry_run !== true}
                            title={!migrateResult || migrateResult.dry_run !== true ? 'Run Dry Run first' : 'Execute migration'}
                        >
                            {loading ? 'Processing...' : '🚀 Run Migration'}
                        </button>
                    </div>

                    {/* Migration Result */}
                    {migrateResult && (
                        <div className={`p-4 rounded border ${migrateResult.dry_run ? 'bg-yellow-50 border-yellow-200' : 'bg-green-50 border-green-200'}`}>
                            <div className="font-medium mb-2">
                                {migrateResult.dry_run ? '🔍 Dry Run Result (Preview)' : '✅ Migration Complete'}
                            </div>

                            {migrateResult.dry_run ? (
                                <div className="space-y-2 text-sm">
                                    <div>Planned inserts: <strong>{migrateResult.planned_inserts_count?.toLocaleString()}</strong></div>
                                    <div>Columns to insert: <span className="text-xs font-mono">{migrateResult.columns_to_insert?.join(', ')}</span></div>
                                    {migrateResult.potential_issues && migrateResult.potential_issues.length > 0 && (
                                        <div className="text-orange-600">
                                            Issues: {migrateResult.potential_issues.join(', ')}
                                        </div>
                                    )}
                                    <div className="text-green-700 font-medium mt-2">
                                        ✅ Dry run successful. Click "Run Migration" to execute.
                                    </div>
                                </div>
                            ) : (
                                <div className="space-y-2 text-sm">
                                    <div className="text-green-700">Inserted: <strong>{migrateResult.inserted_count?.toLocaleString()}</strong></div>
                                    <div className="text-gray-600">Skipped (conflicts): <strong>{migrateResult.skipped_conflicts_count?.toLocaleString()}</strong></div>
                                    <div className="text-red-600">Errors: <strong>{migrateResult.errors_count?.toLocaleString()}</strong></div>

                                    {/* Batch logs */}
                                    {migrateResult.batch_logs && migrateResult.batch_logs.length > 0 && (
                                        <div className="mt-2">
                                            <div className="font-medium text-xs mb-1">Batch Log:</div>
                                            <div className="bg-gray-900 text-gray-100 rounded p-2 text-xs font-mono max-h-40 overflow-auto">
                                                {migrateResult.batch_logs.map((log, idx) => (
                                                    <div key={idx}>{log}</div>
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                    <div className="mt-2">
                                        <button
                                            className="text-sm text-blue-600 underline"
                                            onClick={handleCompareData}
                                        >
                                            Re-run comparison to see updated status
                                        </button>
                                    </div>
                                </div>
                            )}
                        </div>
                    )}
                </div>
            )}

            {/* No data yet */}
            {!schemaResult && !error && (
                <div className="p-8 text-center text-gray-500 border rounded bg-gray-50">
                    Select Source and Target tables, then click "Compare Schema" to begin.
                </div>
            )}
        </div>
    );
};

export default TableCompareAndMigrate;
