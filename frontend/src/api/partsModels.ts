import api from '@/lib/apiClient';
import type { PartsModel, NewPartsModel } from '@/types/partsModel';

export interface ListPartsModelsParams {
    search?: string;
    brand_id?: number | null;
    limit?: number;
    offset?: number;
}

export interface ListPartsModelsResponse {
    items: PartsModel[];
    total: number;
}

/**
 * List/search parts models from tbl_parts_models.
 * Supports search by model name and pagination.
 */
export async function listPartsModels(
    params: ListPartsModelsParams = {}
): Promise<ListPartsModelsResponse> {
    const response = await api.get<ListPartsModelsResponse>('/api/sq/parts-models', {
        params: {
            search: params.search || undefined,
            brand_id: params.brand_id !== undefined ? params.brand_id : undefined,
            limit: params.limit || 100,
            offset: params.offset || 0,
        },
    });
    return response.data;
}

/**
 * Create a new parts model in tbl_parts_models.
 * All NOT NULL integer fields will default to 0 if not provided.
 */
export async function createPartsModel(payload: NewPartsModel): Promise<PartsModel> {
    // Ensure all NOT NULL fields have defaults
    const safePayload: NewPartsModel = {
        ...payload,
        buying_price: payload.buying_price ?? 0,
        working: payload.working ?? 0,
        motherboard: payload.motherboard ?? 0,
        battery: payload.battery ?? 0,
        hdd: payload.hdd ?? 0,
        keyboard: payload.keyboard ?? 0,
        memory: payload.memory ?? 0,
        screen: payload.screen ?? 0,
        casing: payload.casing ?? 0,
        drive: payload.drive ?? 0,
        damage: payload.damage ?? 0,
        cd: payload.cd ?? 0,
        adapter: payload.adapter ?? 0,
        do_not_buy: payload.do_not_buy ?? false,
    };

    const response = await api.post<PartsModel>('/api/sq/parts-models', safePayload);
    return response.data;
}
