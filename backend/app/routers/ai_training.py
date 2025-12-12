"""AI Training Center router - Phase 2

Admin-only endpoints for training AI Assistant via voice and text.
Allows creating sessions, recording examples, approving outputs,
and promoting examples to semantic rules.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime

from app.models_sqlalchemy import get_db
from app.services.admin_auth import get_current_admin_user
from app.utils.logger import logger

router = APIRouter(prefix="/api/ai-training", tags=["ai-training"])


# ================== Schemas ==================

class TrainingSessionCreate(BaseModel):
    domain: str  # "analytics" | "email" | "case"
    title: str
    notes: Optional[str] = None


class TrainingSessionResponse(BaseModel):
    id: str
    user_id: str
    domain: str
    title: str
    notes: Optional[str]
    started_at: datetime
    ended_at: Optional[datetime]
    examples_count: int = 0


class TrainingExampleCreate(BaseModel):
    session_id: str
    domain: str
    input_mode: str  # "voice" | "text"
    raw_input_text: str
    raw_model_output: dict
    status: str = "draft"


class TrainingExampleUpdate(BaseModel):
    final_approved_output: Optional[dict] = None
    status: Optional[str] = None  # "approved" | "rejected" | "promoted"
    promote_to_rule: bool = False


class TrainingExampleResponse(BaseModel):
    id: str
    session_id: str
    domain: str
    input_mode: str
    raw_input_text: str
    raw_model_output: dict
    final_approved_output: Optional[dict]
    linked_semantic_rule_id: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime


# ================== Endpoints ==================

@router.post("/sessions", response_model=TrainingSessionResponse)
async def create_training_session(
    data: TrainingSessionCreate,
    db: Session = Depends(get_db),
    current_admin = Depends(get_current_admin_user),
):
    """Create new training session (admin only)."""
    
    try:
        result = db.execute(text("""
            INSERT INTO ai_training_sessions (user_id, domain, title, notes)
            VALUES (:user_id, :domain, :title, :notes)
            RETURNING id, user_id, domain, title, notes, started_at, ended_at
        """), {
            "user_id": current_admin.id,
            "domain": data.domain,
            "title": data.title,
            "notes": data.notes,
        })
        
        row = result.fetchone()
        db.commit()
        
        return TrainingSessionResponse(
            id=str(row[0]),
            user_id=str(row[1]),
            domain=row[2],
            title=row[3],
            notes=row[4],
            started_at=row[5],
            ended_at=row[6],
            examples_count=0,
        )
    
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create training session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create session: {str(e)}"
        )


@router.get("/sessions", response_model=List[TrainingSessionResponse])
async def list_training_sessions(
    domain: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    _admin = Depends(get_current_admin_user),
):
    """List training sessions (admin only)."""
    
    try:
        where_clause = ""
        params = {"limit": limit}
        
        if domain:
            where_clause = "WHERE s.domain = :domain"
            params["domain"] = domain
        
        query = f"""
            SELECT 
                s.id, s.user_id, s.domain, s.title, s.notes, 
                s.started_at, s.ended_at,
                COUNT(e.id) as examples_count
            FROM ai_training_sessions s
            LEFT JOIN ai_training_examples e ON e.session_id = s.id
            {where_clause}
            GROUP BY s.id
            ORDER BY s.started_at DESC
            LIMIT :limit
        """
        
        result = db.execute(text(query), params)
        rows = result.fetchall()
        
        return [
            TrainingSessionResponse(
                id=str(row[0]),
                user_id=str(row[1]),
                domain=row[2],
                title=row[3],
                notes=row[4],
                started_at=row[5],
                ended_at=row[6],
                examples_count=row[7] or 0,
            )
            for row in rows
        ]
    
    except Exception as e:
        logger.error(f"Failed to list sessions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list sessions: {str(e)}"
        )


@router.post("/examples", response_model=TrainingExampleResponse)
async def create_training_example(
    data: TrainingExampleCreate,
    db: Session = Depends(get_db),
    current_admin = Depends(get_current_admin_user),
):
    """Create training example (admin only)."""
    
    try:
        result = db.execute(text("""
            INSERT INTO ai_training_examples (
                session_id, domain, input_mode, raw_input_text,
                raw_model_output, status, created_by, updated_by
            )
            VALUES (
                :session_id, :domain, :input_mode, :raw_input_text,
                :raw_model_output, :status, :user_id, :user_id
            )
            RETURNING id, session_id, domain, input_mode, raw_input_text,
                      raw_model_output, final_approved_output, linked_semantic_rule_id,
                      status, created_at, updated_at
        """), {
            "session_id": data.session_id,
            "domain": data.domain,
            "input_mode": data.input_mode,
            "raw_input_text": data.raw_input_text,
            "raw_model_output": data.raw_model_output,
            "status": data.status,
            "user_id": current_admin.id,
        })
        
        row = result.fetchone()
        db.commit()
        
        return TrainingExampleResponse(
            id=str(row[0]),
            session_id=str(row[1]),
            domain=row[2],
            input_mode=row[3],
            raw_input_text=row[4],
            raw_model_output=row[5],
            final_approved_output=row[6],
            linked_semantic_rule_id=str(row[7]) if row[7] else None,
            status=row[8],
            created_at=row[9],
            updated_at=row[10],
        )
    
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create example: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create example: {str(e)}"
        )


@router.patch("/examples/{example_id}", response_model=TrainingExampleResponse)
async def update_training_example(
    example_id: str,
    data: TrainingExampleUpdate,
    db: Session = Depends(get_db),
    current_admin = Depends(get_current_admin_user),
):
    """Update training example and optionally promote to semantic rule."""
    
    try:
        # Update example
        update_fields = []
        params = {"example_id": example_id, "user_id": current_admin.id}
        
        if data.final_approved_output is not None:
            update_fields.append("final_approved_output = :approved_output")
            params["approved_output"] = data.final_approved_output
        
        if data.status:
            update_fields.append("status = :status")
            params["status"] = data.status
        
        if update_fields:
            update_fields.append("updated_by = :user_id")
            update_fields.append("updated_at = NOW()")
            
            query = f"""
                UPDATE ai_training_examples
                SET {', '.join(update_fields)}
                WHERE id = :example_id
                RETURNING id, session_id, domain, input_mode, raw_input_text,
                          raw_model_output, final_approved_output, linked_semantic_rule_id,
                          status, created_at, updated_at
            """
            
            result = db.execute(text(query), params)
            row = result.fetchone()
            
            if not row:
                raise HTTPException(status_code=404, detail="Example not found")
            
            # Promote to semantic rule if requested
            rule_id = row[7]
            if data.promote_to_rule and data.final_approved_output:
                rule_id = await _promote_to_semantic_rule(
                    db=db,
                    example_id=example_id,
                    domain=row[2],
                    user_pattern=row[4],
                    approved_output=data.final_approved_output,
                    user_id=current_admin.id,
                )
            
            db.commit()
            
            return TrainingExampleResponse(
                id=str(row[0]),
                session_id=str(row[1]),
                domain=row[2],
                input_mode=row[3],
                raw_input_text=row[4],
                raw_model_output=row[5],
                final_approved_output=row[6],
                linked_semantic_rule_id=str(rule_id) if rule_id else None,
                status=row[8],
                created_at=row[9],
                updated_at=row[10],
            )
        
        else:
            raise HTTPException(status_code=400, detail="No updates provided")
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update example: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update example: {str(e)}"
        )


# ================== Helper Functions ==================

async def _promote_to_semantic_rule(
    db: Session,
    example_id: str,
    domain: str,
    user_pattern: str,
    approved_output: dict,
    user_id: str,
) -> str:
    """Create semantic rule from approved training example."""
    
    # Extract SQL from approved output (if analytics domain)
    sql_template = approved_output.get("sql") if domain == "analytics" else None
    description = approved_output.get("explanation", "")
    
    # Create semantic rule
    result = db.execute(text("""
        INSERT INTO ai_semantic_rules (
            locale, domain, user_pattern, target_description,
            target_sql_template, target_action_type, confidence,
            is_active, created_by, updated_by
        )
        VALUES (
            'ru-RU', :domain, :user_pattern, :description,
            :sql_template, 'GENERATE_SQL', 0.8,
            true, :user_id, :user_id
        )
        RETURNING id
    """), {
        "domain": domain,
        "user_pattern": user_pattern,
        "description": description,
        "sql_template": sql_template,
        "user_id": user_id,
    })
    
    rule_id = result.scalar()
    
    # Link example to rule
    db.execute(text("""
        UPDATE ai_training_examples
        SET linked_semantic_rule_id = :rule_id,
            status = 'promoted'
        WHERE id = :example_id
    """), {"rule_id": rule_id, "example_id": example_id})
    
    logger.info(f"Promoted example {example_id} to semantic rule {rule_id}")
    
    return str(rule_id)
