/**
 * Types for tbl_parts_models table (computer parts models dictionary).
 * Used for model selection and creation in the SKU form.
 */

export interface PartsModel {
    // Primary key
    id: number;

    // Foreign keys & identifiers
    model_id?: number | null;
    brand_id?: number | null;

    // Model name/description
    model: string;

    // OpenCart filter IDs
    oc_filter_model_id?: number | null;
    oc_filter_model_id2?: number | null;

    // Pricing & condition scores (all NOT NULL in DB, default to 0)
    buying_price: number;
    working: number;
    motherboard: number;
    battery: number;
    hdd: number;
    keyboard: number;
    memory: number;
    screen: number;
    casing: number;
    drive: number;
    damage: number;
    cd: number;
    adapter: number;

    // Metadata
    record_created?: string | null;
    do_not_buy?: boolean | null;
}

/**
 * Payload for creating a new parts model.
 * Omits auto-generated fields (id, record_created).
 */
export type NewPartsModel = Omit<PartsModel, "id" | "record_created">;

/**
 * Compact model option for dropdowns/search results.
 */
export interface ModelOption {
    id: number;
    label: string;
    brand_id?: number | null;
    model: string;
}
