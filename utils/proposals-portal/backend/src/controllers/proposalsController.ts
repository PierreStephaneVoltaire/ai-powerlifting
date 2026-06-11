import { Request, Response, NextFunction } from 'express';
import {
  getProposalsByStatus,
  getProposal,
  createProposal,
  updateProposalStatus,
  deleteProposal,
  getDirectives,
  OPERATOR_PK,
} from '../db/dynamodb';
import { generateImplementationPlan } from '../services/planGenerator';
import { createError } from '../middleware/errorHandler';

export async function listProposals(
  req: Request,
  res: Response,
  next: NextFunction
): Promise<void> {
  try {
    const { status, type, author, q } = req.query;

    let proposals = await getProposalsByStatus(OPERATOR_PK);

    // Apply filters
    if (status) {
      proposals = proposals.filter((p) => p.status === status);
    }
    if (type) {
      proposals = proposals.filter((p) => p.type === type);
    }
    if (author) {
      proposals = proposals.filter((p) => p.author === author);
    }
    if (q) {
      const searchLower = (q as string).toLowerCase();
      proposals = proposals.filter(
        (p) =>
          p.title.toLowerCase().includes(searchLower) ||
          p.rationale.toLowerCase().includes(searchLower)
      );
    }

    // Sort by created_at descending
    proposals.sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    );

    res.json({
      proposals,
      total: proposals.length,
    });
  } catch (error) {
    next(error);
  }
}

export async function getProposalById(
  req: Request,
  res: Response,
  next: NextFunction
): Promise<void> {
  try {
    const { sk } = req.params;
    const proposal = await getProposal(OPERATOR_PK, decodeURIComponent(sk));

    if (!proposal) {
      throw createError('Proposal not found', 404);
    }

    res.json({ proposal });
  } catch (error) {
    next(error);
  }
}

export async function createNewProposal(
  req: Request,
  res: Response,
  next: NextFunction
): Promise<void> {
  try {
    const { type, title, rationale, content, target_id } = req.body;

    if (!title || !rationale) {
      throw createError('Title and rationale are required');
    }

    const now = new Date().toISOString();
    const sk = `proposal#${now}`;

    const proposal = {
      pk: OPERATOR_PK,
      sk,
      type: type || 'system_observation',
      status: 'pending',
      author: 'user',
      title,
      rationale,
      content: content || '',
      target_id: target_id || null,
      implementation_plan: null,
      created_at: now,
      resolved_at: null,
      resolved_by: null,
      rejection_reason: null,
    };

    await createProposal(proposal);

    res.status(201).json({ proposal });
  } catch (error) {
    next(error);
  }
}

export async function approveProposal(
  req: Request,
  res: Response,
  next: NextFunction
): Promise<void> {
  try {
    const { sk } = req.params;
    const now = new Date().toISOString();

    // Mark as approved first so the user gets immediate feedback
    const updated = await updateProposalStatus(OPERATOR_PK, decodeURIComponent(sk), {
      status: 'approved',
      resolved_at: now,
      resolved_by: 'user',
    });

    if (!updated) {
      throw createError('Proposal not found', 404);
    }

    // Generate the implementation plan synchronously and persist it.
    // If generation fails we still keep the approval — the user can retry via
    // POST /:sk/generate-plan.
    try {
      const directives = await getDirectives(OPERATOR_PK);
      const plan = await generateImplementationPlan(updated, directives);
      const withPlan = await updateProposalStatus(OPERATOR_PK, decodeURIComponent(sk), {
        implementation_plan: plan,
      });
      res.json({ proposal: withPlan ?? { ...updated, implementation_plan: plan } });
      return;
    } catch (planErr) {
      console.error('Plan generation failed during approve:', planErr);
      res.json({ proposal: updated });
      return;
    }
  } catch (error) {
    next(error);
  }
}

export async function rejectProposal(
  req: Request,
  res: Response,
  next: NextFunction
): Promise<void> {
  try {
    const { sk } = req.params;
    const { reason } = req.body;
    const now = new Date().toISOString();

    const proposal = await updateProposalStatus(OPERATOR_PK, decodeURIComponent(sk), {
      status: 'rejected',
      resolved_at: now,
      resolved_by: 'user',
      rejection_reason: reason || null,
    });

    if (!proposal) {
      throw createError('Proposal not found', 404);
    }

    res.json({ proposal });
  } catch (error) {
    next(error);
  }
}

export async function deleteProposalById(
  req: Request,
  res: Response,
  next: NextFunction
): Promise<void> {
  try {
    const { sk } = req.params;
    const deleted = await deleteProposal(OPERATOR_PK, decodeURIComponent(sk));

    if (!deleted) {
      throw createError(
        'Proposal not found or cannot be deleted (only pending proposals can be deleted)',
        400
      );
    }

    res.status(204).send();
  } catch (error) {
    next(error);
  }
}

export async function generatePlan(
  req: Request,
  res: Response,
  next: NextFunction
): Promise<void> {
  try {
    const { sk } = req.params;
    const proposal = await getProposal(OPERATOR_PK, decodeURIComponent(sk));

    if (!proposal) {
      throw createError('Proposal not found', 404);
    }

    if (proposal.status !== 'approved') {
      throw createError('Can only generate plans for approved proposals', 400);
    }

    const directives = await getDirectives(OPERATOR_PK);
    const plan = await generateImplementationPlan(proposal, directives);
    const updated = await updateProposalStatus(OPERATOR_PK, decodeURIComponent(sk), {
      implementation_plan: plan,
    });

    res.json({ proposal: updated ?? { ...proposal, implementation_plan: plan }, plan });
  } catch (error) {
    next(error);
  }
}

export async function getPlan(
  req: Request,
  res: Response,
  next: NextFunction
): Promise<void> {
  try {
    const { sk } = req.params;
    const proposal = await getProposal(OPERATOR_PK, decodeURIComponent(sk));

    if (!proposal) {
      throw createError('Proposal not found', 404);
    }

    res.json({ plan: proposal.implementation_plan });
  } catch (error) {
    next(error);
  }
}
