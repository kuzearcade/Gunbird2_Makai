// Seed function starts: SHC-style prologues after rts/delay slot, and literal-pool code pointers.
// args: [lo hi]  (hex range of code to scan)
import ghidra.app.script.GhidraScript;
import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.program.model.address.*;
import ghidra.program.model.mem.*;
import ghidra.program.model.listing.*;

public class SeedFunctions extends GhidraScript {
    boolean isPush(int w) {
        return (w & 0xF00F) == 0x2006 && ((w >> 8) & 0xF) == 0xF   // mov.l Rm,@-r15
            || w == 0x4F22                                          // sts.l pr,@-r15
            || (w & 0xFF00) == 0x7F00 && (w & 0x80) != 0;           // add #-n,r15
    }
    @Override
    public void run() throws Exception {
        String[] a = getScriptArgs();
        AddressSpace sp = currentProgram.getAddressFactory().getDefaultAddressSpace();
        long lo = Long.parseLong(a[0], 16), hi = Long.parseLong(a[1], 16);
        Memory mem = currentProgram.getMemory();
        Listing lst = currentProgram.getListing();
        int n = 0;
        for (Function f : currentProgram.getFunctionManager().getFunctions(sp.getAddress(lo), true)) {
            if (f.getEntryPoint().getOffset() >= hi) break;
            new DisassembleCommand(f.getEntryPoint(), null, true).applyTo(currentProgram, monitor);
        }
        analyzeChanges(currentProgram);
        for (int pass = 0; pass < 3; pass++) {
            for (long x = lo + 4; x < hi - 2; x += 2) {
                Address ad = sp.getAddress(x);
                if (lst.getInstructionAt(ad) != null && getFunctionAt(ad) != null) continue;
                int w = mem.getShort(ad) & 0xffff;
                if (!isPush(w) && w != 0x4F12) continue;
                int p2 = mem.getShort(sp.getAddress(x - 4)) & 0xffff;
                int p1 = mem.getShort(sp.getAddress(x - 2)) & 0xffff;
                boolean afterRet = p2 == 0x000B || (p2 & 0xF0FF) == 0x402B  // rts / jmp @Rn + delay
                                 || p1 == 0x0009 && (mem.getShort(sp.getAddress(x - 6)) & 0xffff) == 0x000B
                                 || lst.getDefinedDataContaining(sp.getAddress(x - 2)) != null;
                if (!afterRet && lst.getInstructionContaining(sp.getAddress(x - 2)) == null) {
                    int pushes = 0;
                    for (int k = 0; k < 8; k++) {
                        int u = mem.getShort(sp.getAddress(x + 2 * k)) & 0xffff;
                        if (isPush(u) || u == 0x4F12) pushes++;
                    }
                    afterRet = pushes >= 2;
                }
                if (!afterRet) continue;
                if (lst.getInstructionAt(ad) == null) {
                    if (lst.getDefinedDataContaining(ad) != null) continue;
                    new DisassembleCommand(ad, null, true).applyTo(currentProgram, monitor);
                }
                if (getFunctionAt(ad) == null && createFunction(ad, null) != null) n++;
            }
            // any aligned pointer anywhere in initialized RAM images / data ROM that targets a prologue
            for (MemoryBlock b : mem.getBlocks()) {
                if (!b.isInitialized()) continue;
                long s0 = (b.getStart().getOffset() + 3) & ~3L, e0 = b.getEnd().getOffset() - 3;
                for (long x = s0; x < e0; x += 4) {
                    long v = mem.getInt(sp.getAddress(x)) & 0xffffffffL;
                    if (v < lo || v >= hi || (v & 1) != 0) continue;
                    Address t = sp.getAddress(v);
                    if (getFunctionAt(t) != null) continue;
                    int w = mem.getShort(t) & 0xffff;
                    if (!isPush(w) && w != 0x4F12) continue;
                    if (lst.getDefinedDataContaining(t) != null) continue;
                    new DisassembleCommand(t, null, true).applyTo(currentProgram, monitor);
                    if (createFunction(t, null) != null) n++;
                }
            }
            analyzeChanges(currentProgram);
            println("pass " + pass + " total created " + n + " functions now " + currentProgram.getFunctionManager().getFunctionCount());
        }
    }
}
